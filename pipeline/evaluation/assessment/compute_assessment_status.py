#!/usr/bin/env python3
"""
Compute the assessment status of every judged field (docs/ASSESSMENT_STATUS_SPEC.md).

The status is derived, never stored in the corpus. It is computed from the
three places where assessments are already recorded:

  llm_judge   pipeline/evaluation/llm_judge/runs/<run_id>/{judge}.jsonl
  human       pipeline/evaluation/llm_judge/runs/<run_id>/human/review_*.json
  corrected   _provenance.activities[type=manual_edit].corrected_values (JSON)

and is tied to the value each assessment saw, not to an RDF URI. A field's
state is the highest level whose assessment still matches the current value:

  3 human_corrected > 2 human_reviewed > 1 llm_judged > 0 unassessed

An assessment whose value has changed since no longer counts; the field drops
to the next level and keeps `stale_from` = the highest level it lost.

Fields are the judged leaf paths of judge_common.flatten (persons,
communities, person_relationships; context-only keys excluded).

Output: pipeline/evaluation/assessment/assessment_status.json
  summary   counts per inscription status and per field state
  records   {edcs_id: ...} for every inscription with any assessment
            (inscriptions not listed are unassessed in every field)

Usage:
  python compute_assessment_status.py            # write assessment_status.json
  python compute_assessment_status.py --check    # print the summary only
"""
import argparse
import collections
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "llm_judge"))
from judge_common import (  # noqa: E402
    FIELD_OUTCOMES, RUNS_DIR, build_user_message, field_outcome, flatten, input_sha, iter_records,
    value_map, value_shas,
)

STATES = ["unassessed", "llm_judged", "human_reviewed", "human_corrected"]
RANK = {s: i for i, s in enumerate(STATES)}
OUT = HERE / "assessment_status.json"
SEVERITY = {"minor": 1, "major": 2}


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Evidence loading ──────────────────────────────────────────────────────────

def load_judge_runs():
    """{edcs_id: [run evidence]} — one entry per run that judged the inscription."""
    out = collections.defaultdict(list)
    for meta_path in sorted(RUNS_DIR.glob("*/run_meta.json")):
        run_dir = meta_path.parent
        meta = json.loads(meta_path.read_text())
        expected = sorted(meta.get("judges", {}))
        rows = collections.defaultdict(dict)          # edcs -> judge -> latest ok row
        for judge in expected:
            path = run_dir / f"{judge}.jsonl"
            if not path.exists():
                continue
            for line in path.read_text().splitlines():
                r = json.loads(line)
                if r.get("status") == "ok":
                    rows[r["edcs_id"]][judge] = r
        tiers = {}
        queue = run_dir / "review_queue.json"
        if queue.exists():
            for it in json.loads(queue.read_text()).get("items", []):
                tiers[it["edcs_id"]] = it.get("tier")
        for eid, by_judge in rows.items():
            out[eid].append({
                "run_id": run_dir.name,
                "prompt_hash": meta.get("prompt_hash"),
                "expected": expected,
                "rows": by_judge,
                "complete": set(expected) <= set(by_judge),
                "models": {j: (meta["judges"][j] or {}).get("model") for j in expected},
                "tier": tiers.get(eid),
                "timestamp": max(r.get("timestamp", "") for r in by_judge.values()),
            })
    return out


def load_human_reviews():
    """{edcs_id: [review]} from runs/*/human/review_*.json."""
    out = collections.defaultdict(list)
    for path in sorted(RUNS_DIR.glob("*/human/review_*.json")):
        rv = json.loads(path.read_text())
        rv["_file"] = str(path.relative_to(RUNS_DIR))
        out[rv["edcs_id"]].append(rv)
    return out


# ── Per-record computation ────────────────────────────────────────────────────

def changed_after(rec, ts):
    """True if a non-manual activity ran on the record after `ts`."""
    for a in (rec.get("_provenance") or {}).get("activities", []):
        if a.get("type") != "manual_edit" and (a.get("timestamp") or "") > ts:
            return True
    return False


def assess_record(rec, judge_runs, reviews, warnings):
    eid = rec["edcs_id"]
    _, judged, _ = flatten(rec)
    universe = sorted(judged)
    cur_fp = value_shas(rec)
    cur_sha = input_sha(build_user_message(rec))
    cur_text = value_map(rec)

    fresh = collections.defaultdict(int)       # path -> highest fresh rank
    stale = collections.defaultdict(int)       # path -> highest stale rank
    # path -> (run timestamp, run_id, {judge: {verdict, severity}}) from the
    # latest counted run whose judgement still applies to the current value.
    judge_latest = {}
    container_latest = {}                      # same, for list/object paths
    evidence = []
    # Whole-record assessments, for records with no judged field at all
    # (nothing was extracted): their status comes from these alone.
    record_rank = {"fresh": 0, "stale": 0}

    def mark(paths, rank, ok, whole_record=False):
        target = fresh if ok else stale
        for p in paths:
            target[p] = max(target[p], rank)
        if whole_record:
            k = "fresh" if ok else "stale"
            record_rank[k] = max(record_rank[k], rank)

    # 1. LLM judge — only runs where every expected judge returned a result
    for run in judge_runs.get(eid, []):
        rows = list(run["rows"].values())
        ev = {"kind": "llm_judge", "run_id": run["run_id"], "timestamp": run["timestamp"],
              "judges_ok": sorted(run["rows"]), "expected": run["expected"],
              "complete": run["complete"], "tier": run["tier"],
              "models": run["models"], "prompt_hash": run["prompt_hash"]}
        if not run["complete"]:
            ev["counted"] = False
            evidence.append(ev)
            continue
        ok_paths = []
        if all("value_shas" in r for r in rows):
            ok_paths = [p for p in universe
                        if all(r["value_shas"].get(p) == cur_fp.get(p) for r in rows)]
            seen = set().union(*(r["value_shas"] for r in rows))
            mark(ok_paths, 1, True)
            mark([], 1, all(set(r["value_shas"]) == set(universe) for r in rows)
                 and len(ok_paths) == len(universe), whole_record=True)
            mark([p for p in seen if p not in ok_paths], 1, False)
            ev["match"] = "field"
            ev["fresh_fields"] = len(ok_paths)
        elif all(r.get("input_sha") for r in rows):
            ok = all(r["input_sha"] == cur_sha for r in rows)
            mark(universe, 1, ok, whole_record=True)
            ok_paths = list(universe) if ok else []
            ev["match"] = "record"
            ev["fresh"] = ok
        else:
            # Neither fingerprints nor an input hash: the judged value is unknown.
            mark(universe, 1, False, whole_record=True)
            ev["match"] = "none"
            ev["fresh"] = False
        ev["counted"] = True
        # Findings of this run, one per judge per path (the more severe kept),
        # recorded only for the fields whose judged value is still current.
        findings = collections.defaultdict(dict)
        for r in rows:
            for iss in (r.get("result") or {}).get("issues", []):
                if not iss.get("path_valid"):
                    continue
                prev = findings[iss["path"]].get(r["judge"])
                if prev is None or SEVERITY.get(iss.get("severity"), 0) > SEVERITY.get(prev["severity"], 0):
                    findings[iss["path"]][r["judge"]] = {"verdict": iss.get("verdict"),
                                                         "severity": iss.get("severity")}
        for p in ok_paths:
            if p not in judge_latest or run["timestamp"] > judge_latest[p][0]:
                judge_latest[p] = (run["timestamp"], run["run_id"], dict(findings.get(p, {})))
        # Findings on a list or object (mostly omissions: "an office is missing
        # from career_path") have no leaf of their own. They count while every
        # field under them is still as judged.
        ok_set = set(ok_paths)
        for p, fj in findings.items():
            if p in universe:
                continue
            under = [u for u in universe if u.startswith(p + ".") or u.startswith(p + "[")]
            if (all(u in ok_set for u in under) if under else len(ok_set) == len(universe)):
                if p not in container_latest or run["timestamp"] > container_latest[p][0]:
                    container_latest[p] = (run["timestamp"], run["run_id"], dict(fj))
        outcomes = ([field_outcome(judge_latest[p][2]) for p in ok_paths if judge_latest[p][1] == run["run_id"]]
                    + [field_outcome(v[2]) for v in container_latest.values() if v[1] == run["run_id"]])
        if outcomes:
            ev["worst_outcome"] = min(outcomes, key=FIELD_OUTCOMES.index)
        evidence.append(ev)

    # 2. Human review of the judge's findings
    for rv in reviews.get(eid, []):
        saved = rv.get("saved_at", "")
        ev = {"kind": "human_review", "run_id": rv.get("run_id"), "editor": rv.get("editor"),
              "timestamp": saved, "done": bool(rv.get("done")), "file": rv["_file"]}
        for path, f in (rv.get("findings") or {}).items():
            if not f.get("verdict"):
                continue
            jv = f.get("judged_value")
            ok = jv is None or cur_text.get(path) == jv
            mark([path], 2, ok)
        if rv.get("done"):
            # Done = the reviewer went through the whole record (spec §2.2).
            ok = not changed_after(rec, saved)
            mark(universe, 2, ok, whole_record=True)
            ev["fresh"] = ok
        evidence.append(ev)

    # 3. Manual corrections applied to the JSON
    for a in (rec.get("_provenance") or {}).get("activities", []):
        if a.get("type") != "manual_edit":
            continue
        cv = a.get("corrected_values")
        if cv is None:
            warnings["manual_edit_without_corrected_values"] += 1
            continue
        for p, fp in cv.items():
            mark([p], 3, cur_fp.get(p) == fp)
        evidence.append({"kind": "manual_edit", "activity_id": a.get("activity_id"),
                         "editor": a.get("editor"), "timestamp": a.get("timestamp"),
                         "fields": len(cv)})

    if not evidence:
        return None

    fields = {}
    for p in universe:
        f = {"state": STATES[fresh[p]]}
        if stale[p] > fresh[p]:
            f["stale_from"] = STATES[stale[p]]
        if p in judge_latest:
            _, run_id, fj = judge_latest[p]
            f["outcome"] = field_outcome(fj)
            if fj:
                f["judge"] = {"run_id": run_id, "flagged_by": sorted(fj),
                              "severity": max((x["severity"] for x in fj.values()),
                                              key=lambda s: SEVERITY.get(s, 0)),
                              "verdicts": {j: x["verdict"] for j, x in sorted(fj.items())}}
        fields[p] = f
    counts = collections.Counter(f["state"] for f in fields.values())
    if fields:
        lowest = min(RANK[f["state"]] for f in fields.values())
        highest = max(RANK[f["state"]] for f in fields.values())
        stale_from = max((RANK[f["stale_from"]] for f in fields.values() if "stale_from" in f),
                         default=None)
    else:
        lowest = highest = record_rank["fresh"]
        stale_from = record_rank["stale"] if record_rank["stale"] > lowest else None
    containers = {}
    for p, (_, run_id, fj) in sorted(container_latest.items()):
        containers[p] = {"outcome": field_outcome(fj), "judge": {
            "run_id": run_id, "flagged_by": sorted(fj),
            "severity": max((x["severity"] for x in fj.values()), key=lambda s: SEVERITY.get(s, 0)),
            "verdicts": {j: x["verdict"] for j, x in sorted(fj.items())}}}
    outcome_counts = collections.Counter(f["outcome"] for f in list(fields.values()) + list(containers.values())
                                         if "outcome" in f)
    return {
        "edcs_id": eid,
        "input_sha": cur_sha,
        **({"worst_outcome": min(outcome_counts, key=FIELD_OUTCOMES.index)} if outcome_counts else {}),
        "outcome_counts": {o: outcome_counts[o] for o in FIELD_OUTCOMES if outcome_counts[o]},
        "status": STATES[lowest],
        "highest": STATES[highest],
        **({"stale_from": STATES[stale_from]} if stale_from is not None else {}),
        "field_counts": {s: counts.get(s, 0) for s in STATES},
        "stale_fields": sum(1 for f in fields.values() if "stale_from" in f),
        "evidence": evidence,
        "fields": fields,
        "containers": containers,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--check", action="store_true", help="print the summary, do not write")
    args = ap.parse_args()

    judge_runs = load_judge_runs()
    reviews = load_human_reviews()
    warnings = collections.Counter()
    records, n_total = {}, 0
    status_counts = collections.Counter()
    field_counts = collections.Counter()
    outcome_totals = collections.Counter()
    container_totals = collections.Counter()
    for _, rec in iter_records():
        n_total += 1
        res = assess_record(rec, judge_runs, reviews, warnings)
        if res is None:
            status_counts["unassessed"] += 1
            continue
        records[rec["edcs_id"]] = res
        status_counts[res["status"]] += 1
        if res.get("stale_from") and res["status"] == "unassessed":
            status_counts["unassessed (stale)"] += 1
        field_counts.update(f["state"] for f in res["fields"].values())
        outcome_totals.update(f["outcome"] for f in res["fields"].values() if "outcome" in f)
        container_totals.update(f["outcome"] for f in res["containers"].values())

    summary = {
        "generated_at": now(),
        "inscriptions": n_total,
        "by_status": {s: status_counts.get(s, 0) for s in STATES},
        "unassessed_stale": status_counts.get("unassessed (stale)", 0),
        "assessed_records_listed": len(records),
        "field_states_in_listed_records": {s: field_counts.get(s, 0) for s in STATES},
        "judge_outcomes_of_current_fields": {o: outcome_totals.get(o, 0) for o in FIELD_OUTCOMES},
        "judge_outcomes_of_lists_and_objects": {o: container_totals.get(o, 0) for o in FIELD_OUTCOMES
                                                if o != "no_finding"},
        "inscriptions_by_worst_outcome": dict(collections.Counter(
            r.get("worst_outcome", "none") for r in records.values())),
        "judge_runs": sorted({e["run_id"] for v in judge_runs.values() for e in v}),
        "human_review_files": sum(len(v) for v in reviews.values()),
        "warnings": dict(warnings),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if not args.check:
        Path(args.out).write_text(json.dumps({"format_version": "1.0", "summary": summary,
                                              "records": records}, ensure_ascii=False, indent=1))
        print(f"-> {args.out}")


if __name__ == "__main__":
    main()
