#!/usr/bin/env python3
"""
Combine the format check and the three judges into a human-review queue.

Usage
-----
  python build_review_queue.py --run-id pilot01
  python build_review_queue.py --run-id full01 --audit-n 300 --seed 7

Tiers (review order)
--------------------
A field is a *major consensus* field when at least two judges call it major.

  format      deterministic format errors (validate_career_graphs.py)
  agree_all   a major-consensus field flagged by every judge that returned a result
  agree_2     a major-consensus field flagged by two judges
  single      a field only one judge calls major
  unjudged    no judge result (too large, or every call failed)
  audit       random sample of the deprioritised inscriptions (minor_only + clean);
              shown blind
  minor_only  only minor findings — not queued except through audit
  clean       no findings — not queued except through audit

Severity drives the tiers because the pilot (pilot02, 2026-11-22) showed all
three judges agreeing on minor, corpus-wide defects (paraphrased
gender_evidence / ethnicity_evidence) in nearly every inscription; ranking by
agreement alone put 26 of 30 inscriptions in the top tier. Such recurring
minor findings are reported once, as corpus-level patterns, in agreement.json.

Within a tier, inscriptions with more major-consensus fields, then more
flagged fields, come first. `audit` exists to estimate what the judges miss:
without it, a pass from every judge cannot be distinguished from a shared
blind spot.

Findings are matched across judges by exact path. Two judges flagging
`persons[0].gender` and `persons[0].gender_evidence` count as two different
fields; the editor shows them side by side.

Output: runs/<run_id>/review_queue.json, runs/<run_id>/agreement.json
"""

import argparse
import itertools
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from judge_common import RUNS_DIR, flatten, inscription_header, load_record, value_map  # noqa: E402
from validate_career_graphs import validate_inscription_issues  # noqa: E402

TIER_ORDER = ["format", "agree_all", "agree_2", "single", "unjudged", "audit"]
NOT_QUEUED = ["minor_only", "clean"]


def load_judge_rows(run_dir, judges):
    """Latest row per (judge, key); a later successful retry wins over an error."""
    rows = {}
    for j in judges:
        path = run_dir / f"{j}.jsonl"
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            r = json.loads(line)
            prev = rows.get((j, r["key"]))
            if prev is None or prev["status"] != "ok":
                rows[(j, r["key"])] = r
    return rows


def build_item(key, rec, judges, rows):
    errors, warnings = validate_inscription_issues(rec, path="$")
    judge_status, overall, notes = {}, {}, {}
    by_path = defaultdict(dict)
    for j in judges:
        r = rows.get((j, key))
        judge_status[j] = r["status"] if r else "missing"
        if not r or r["status"] != "ok":
            continue
        res = r["result"]
        overall[j] = res.get("overall")
        if res.get("note"):
            notes[j] = res["note"]
        for iss in res.get("issues", []):
            # one finding per judge per path; keep the more severe
            prev = by_path[iss["path"]].get(j)
            if prev is None or (prev["severity"] == "minor" and iss["severity"] == "major"):
                by_path[iss["path"]][j] = {k: iss[k] for k in
                                           ("verdict", "severity", "reason", "suggested_value", "path_valid")}

    ok_judges = [j for j in judges if judge_status[j] == "ok"]
    # Value at judging time (every judge saw the same input). Rows written
    # before run_judge.py recorded it fall back to the current data.
    judged_vals = {}
    for j in ok_judges:
        judged_vals.update(rows[(j, key)].get("flagged_values") or {})
    live = value_map(rec)
    flagged = []
    for path, fj in by_path.items():
        known = any(path in (rows[(j, key)].get("flagged_values") or {}) for j in fj)
        flagged.append({
            "path": path,
            "judged_value": judged_vals.get(path) if known else live.get(path),
            "judged_value_known": known,
            "n_flag": len(fj),
            "n_major": sum(1 for f in fj.values() if f["severity"] == "major"),
            "judges": fj,
        })
    flagged.sort(key=lambda f: (-f["n_flag"], -f["n_major"], f["path"]))

    consensus = [f for f in flagged if f["n_major"] >= 2]
    max_flag = max((f["n_flag"] for f in consensus), default=0)
    if errors:
        tier = "format"
    elif not ok_judges:
        tier = "unjudged"
    elif consensus and max_flag == len(ok_judges):
        tier = "agree_all"
    elif consensus:
        tier = "agree_2"
    elif any(f["n_major"] for f in flagged):
        tier = "single"
    elif flagged:
        tier = "minor_only"
    else:
        tier = "clean"

    meta, text = inscription_header(rec)
    return {
        "key": key,
        "edcs_id": rec.get("edcs_id"),
        "tier": tier,
        "audit": False,
        "score": [len(consensus), sum(f["n_major"] for f in flagged), len(flagged)],
        "metadata": meta,
        "inscription": text,
        "extraction": flatten(rec)[0],
        "format_errors": errors,
        "format_warnings": warnings,
        "judge_status": judge_status,
        "judge_overall": overall,
        "judge_notes": notes,
        "flagged": flagged,
    }


def fleiss_kappa(table):
    """table: list of per-item category counts (same number of raters per item)."""
    if not table:
        return None
    n = sum(table[0])
    N, k = len(table), len(table[0])
    p = [sum(row[c] for row in table) / (N * n) for c in range(k)]
    P = [(sum(x * x for x in row) - n) / (n * (n - 1)) for row in table]
    Pbar, Pe = sum(P) / N, sum(x * x for x in p)
    return None if Pe == 1 else round((Pbar - Pe) / (1 - Pe), 3)


def agreement(items, judges):
    """Inter-judge agreement, computed only over inscriptions every judge returned."""
    full = [it for it in items if all(it["judge_status"][j] == "ok" for j in judges)]
    out = {"n_inscriptions_all_judges_ok": len(full)}
    if not full:
        return out

    pair = {}
    for a, b in itertools.combinations(judges, 2):
        inter = union = 0
        for it in full:
            pa = {f["path"] for f in it["flagged"] if a in f["judges"]}
            pb = {f["path"] for f in it["flagged"] if b in f["judges"]}
            inter += len(pa & pb)
            union += len(pa | pb)
        pair[f"{a}~{b}"] = {"path_jaccard": round(inter / union, 3) if union else None,
                            "shared_paths": inter, "union_paths": union}
    out["pairwise_path_agreement"] = pair

    # inscription level: does the judge report at least one major problem?
    table = []
    for it in full:
        yes = sum(1 for j in judges
                  if any(j in f["judges"] and f["judges"][j]["severity"] == "major" for f in it["flagged"]))
        table.append([yes, len(judges) - yes])
    out["fleiss_kappa_any_major"] = fleiss_kappa(table) if len(judges) > 1 else None

    # Recurring findings: the same field (indices stripped) flagged by every
    # judge across many inscriptions. These point at the extraction prompt,
    # not at individual records.
    pat = defaultdict(lambda: {"inscriptions": set(), "minor": 0, "major": 0})
    for it in full:
        for f in it["flagged"]:
            if f["n_flag"] == len(judges):
                k = re.sub(r"\[\d+\]", "[]", f["path"])
                pat[k]["inscriptions"].add(it["key"])
                pat[k]["major" if f["n_major"] >= 2 else "minor"] += 1
    out["recurring_patterns"] = sorted(
        ({"field": k, "inscriptions": len(v["inscriptions"]),
          "share": round(len(v["inscriptions"]) / len(full), 3),
          "majority_minor": v["minor"], "majority_major": v["major"]}
         for k, v in pat.items() if len(v["inscriptions"]) >= 2),
        key=lambda x: -x["inscriptions"])

    out["per_judge"] = {
        j: {
            "flagged_paths": sum(1 for it in full for f in it["flagged"] if j in f["judges"]),
            "major": sum(1 for it in full for f in it["flagged"]
                         if j in f["judges"] and f["judges"][j]["severity"] == "major"),
            "invalid_paths": sum(1 for it in full for f in it["flagged"]
                                 if j in f["judges"] and not f["judges"][j]["path_valid"]),
            "overall": dict(Counter(it["judge_overall"].get(j) for it in full)),
        } for j in judges
    }
    return out


BLIND_FIELDS = ("judge_notes", "judge_overall", "flagged")


def build_run(run_id, judges, audit_n=None, seed=42):
    """Return (items, agreement, summary) for a run.

    items holds every target, queued or not, in queue order first. Audit items
    keep their judge output under `blind` so the editor can reveal it once the
    reviewer has recorded a verdict; review_queue.json strips it.
    """
    run_dir = RUNS_DIR / run_id
    targets = json.loads((run_dir / "targets.json").read_text())
    rows = load_judge_rows(run_dir, judges)

    items = [build_item(k, load_record(k), judges, rows) for k in targets]
    # Agreement is computed before audit items are hidden for blind review.
    agr = agreement(items, judges)

    pool = [it for it in items if it["tier"] in NOT_QUEUED]
    n_audit = audit_n if audit_n is not None else (max(1, round(len(pool) * 0.1)) if pool else 0)
    for it in random.Random(seed).sample(pool, min(n_audit, len(pool))):
        it["audit_origin"] = it["tier"]
        it["tier"], it["audit"] = "audit", True
        it["blind"] = {f: it[f] for f in BLIND_FIELDS}
        it["judge_notes"], it["judge_overall"], it["flagged"] = {}, {}, []

    order = TIER_ORDER + NOT_QUEUED
    items.sort(key=lambda it: (order.index(it["tier"]), [-x for x in it["score"]], it["key"]))
    for rank, it in enumerate(items, 1):
        it["rank"] = rank

    tiers = Counter(it["tier"] for it in items)
    summary = {
        "run_id": run_id, "judges": judges, "targets": len(targets),
        "tiers": {t: tiers.get(t, 0) for t in order},
        "queue_length": sum(1 for it in items if it["tier"] in TIER_ORDER), "audit_seed": seed,
    }
    return items, agr, summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--judges", default="claude,gpt,gemini")
    ap.add_argument("--audit-n", type=int, default=None,
                    help="number of deprioritised (minor_only + clean) inscriptions to audit "
                         "(default: 10%% of them, at least 1)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    run_dir = RUNS_DIR / args.run_id
    judges = args.judges.split(",")
    items, agr, summary = build_run(args.run_id, judges, args.audit_n, args.seed)
    queue = [{k: v for k, v in it.items() if k != "blind"} for it in items if it["tier"] in TIER_ORDER]
    (run_dir / "review_queue.json").write_text(
        json.dumps({"summary": summary, "items": queue}, ensure_ascii=False, indent=1))
    (run_dir / "agreement.json").write_text(json.dumps(agr, ensure_ascii=False, indent=2))

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(agr, ensure_ascii=False, indent=2))
    print(f"→ {run_dir/'review_queue.json'}")


if __name__ == "__main__":
    main()
