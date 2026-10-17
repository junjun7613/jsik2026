#!/usr/bin/env python3
"""社会的身分カテゴリ（案C・多値配列）を validated_career_graphs に付与する.

network_analysis/mapping/status_category_map.json の規則を適用し、
persons[] の各人物に social_statuses[] を **追記** する。

    social_statuses[]            身分言明の配列（多軸・案C）
      .category                  第1階層（6種）
      .subtype                   第2階層（確定しない場合は付与しない）
      .rank                      位階（consularis 等。該当時のみ）
      .evidence                  根拠となる原文
      .certainty                 explicit / inferred
      .source                    判定の来歴
    social_status_source         人物単位の処理結果

既存の social_status / social_status_evidence は変更しない。抽出 LLM が
生成し人手校訂の対象でもある別系統の値であり、上書きすると生成来歴が
失われるため。RDF 上でも別プロパティに対応する
（epig:socialStatus と epig:hasSocialStatusStatement）。

役職は career_path に委ねる（SOCIAL_STATUS_INVENTORY.md §9-2）。
委譲対象のうち career_path が当該役職を記録していない人物については、
社会的身分フィールドを失うと情報が完全に消えるため career_path へ移送する。

【重要】evidence からの追加軸の機械的推定は行わない。evidence が同じ碑文の
他の人物を指している場合があり（§4-7。'emperor' の evidence に
'Aug(usti) ser(vus)' = 皇帝の奴隷、等）、語の出現だけで軸を足すと
誤分類になる。多軸の拾い直しは LLM パス（人物同定を含む）に委ねる。

仕様: network_analysis/SOCIAL_STATUS_INVENTORY.md
"""
import argparse
import collections
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
MAP_PATH = REPO_ROOT / "network_analysis/mapping/status_category_map.json"
DEFAULT_CORPUS = SCRIPT_DIR / "validated_career_graphs" / "claude"

SCRIPT_NAME = "classify_social_status.py"
ACTIVITY_TYPE = "classify_social_status"
GENERATED_FIELDS = [
    "persons[].social_statuses",
    "persons[].social_status_source",
]
MIGRATION_FIELDS = [
    "persons[].career_path",
    "persons[].has_career",
]

# 移送時の position_type。既存 career_path での最頻値から決定した（実測）
POSITION_TYPE = {
    "sacerdos": "local-priesthood", "flamen": "local-priesthood",
    "flaminica": "local-priesthood", "augur": "local-priesthood",
    "diaconus": "local-priesthood", "subdiaconus": "local-priesthood",
    "lector": "local-priesthood", "presbyter": "local-priesthood",
    "bishop": "local-priesthood", "archdeacon": "local-priesthood",
    "pontifex": "imperial-priesthood",
    "local-priesthood": "local-priesthood",
    "aedilis": "local-administration", "duovir": "local-administration",
    "quaestor": "local-administration", "quinquennalis": "local-administration",
    "municipal-magistrate": "local-administration",
    "local-administration": "local-administration", "local": "local-administration",
    "consul": "imperial-administration", "tribunus": "imperial-administration",
    "curator": "imperial-administration", "administrator": "imperial-administration",
    "imperial-administration": "imperial-administration",
    "legatus": "provincial-administration",
    "provincial-governor": "provincial-administration",
    "provincial-administration": "provincial-administration",
    "clericus": "other", "military-commander": "military",
    "promagister": "other",
}


def now_compact():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Classifier:
    def __init__(self, spec):
        self.spec = spec
        self.canon = {}
        for k, vs in spec["normalize_surface"]["spelling_variants"].items():
            if k.startswith("$"):
                continue
            for v in vs:
                self.canon[v] = k
        self.delegated = (set(spec["delegated_to_career_path"]["office"])
                          | set(spec["delegated_to_career_path"]["religious_office"]))
        self.excluded = {k for k in spec["excluded_values"] if not k.startswith("$")}
        self.direct = spec["direct_map"]
        self.multi = spec["multi_axis_map"]
        self.ambiguous = spec["ambiguous_forms"]
        self.inf_re = re.compile(spec["certainty"]["inference_markers"], re.I)

    def normalize(self, v):
        s = re.sub(r"\s+", " ", (v or "")).strip().lower()
        return self.canon.get(s, s)

    def certainty(self, evidence):
        return "inferred" if self.inf_re.search(evidence or "") else "explicit"

    def classify(self, status, evidence):
        """(kind, statements, delegate_value) を返す.

        kind: 'empty' | 'excluded' | 'delegated' | 'resolved' | 'pending_llm'
        """
        t = self.normalize(status)
        if not t:
            return "empty", [], None
        if t in self.excluded:
            return "excluded", [], None
        if t in self.delegated:
            return "delegated", [], t

        cert = self.certainty(evidence)
        ev = (evidence or "").strip()

        def mk(d, src):
            s = {"category": d["category"]}
            if d.get("subtype"):
                s["subtype"] = d["subtype"]
            if d.get("rank"):
                s["rank"] = d["rank"]
            if ev:
                s["evidence"] = ev
            s["certainty"] = d.get("certainty", cert)
            if d.get("reasoning"):
                s["reasoning"] = d["reasoning"]
            s["source"] = src
            return s

        if t in self.multi:
            out, deleg = [], None
            for d in self.multi[t]:
                if d.get("category") == "_delegated":
                    deleg = d.get("value")
                else:
                    out.append(mk(d, "multi_axis"))
            return ("resolved" if out else "delegated"), out, deleg

        if t in self.ambiguous:
            a = self.ambiguous[t]
            for d in a.get("disambiguate_by_evidence", []):
                if not re.search(d["pattern"], ev, re.I):
                    continue
                if "multi" in d:
                    out, deleg = [], None
                    for x in d["multi"]:
                        if x.get("category") == "_delegated":
                            deleg = x.get("value")
                        else:
                            out.append(mk(x, "ambiguous"))
                    return ("resolved" if out else "delegated"), out, deleg
                if d.get("category") == "_delegated":
                    return "delegated", [], d.get("value")
                return "resolved", [mk(d, "ambiguous")], None
            # evidence で判別できない → 既定値はあるが LLM の確認が要る
            if a.get("default"):
                s = mk(a["default"], "ambiguous_default")
                s["needs_llm"] = True
                return "resolved", [s], None
            return "pending_llm", [], None

        if t in self.direct:
            d = self.direct[t]
            if d.get("needs_llm") or not d.get("category"):
                return "pending_llm", [], None
            return "resolved", [mk(d, "direct")], None

        return "pending_llm", [], None


def make_career_entry(value, evidence, order):
    """委譲対象を career_path のエントリに変換する."""
    # position_normalized / position_description はスキーマ上 str 必須
    # （location 系と異なり None を許さない）。実測で確認済み。
    return {
        "position": evidence or value,
        "position_normalized": value,
        "position_abstract": value,
        "position_type": POSITION_TYPE.get(value, "other"),
        "position_description": "Migrated from social_status; "
                                "no description recorded at extraction time",
        "order": order,
        "location": None,
        "location_normalized": None,
        "location_evidence": None,
        "migrated_from": "social_status",
    }


def career_mentions(person, value, evidence):
    """career_path が当該役職を既に記録しているか."""
    blob = " ".join(
        " ".join(str(c.get(k) or "") for k in
                 ("position", "position_abstract", "position_normalized"))
        for c in (person.get("career_path") or [])
    ).lower()
    if not blob:
        return False
    if value.lower()[:5] in blob:
        return True
    e = (evidence or "").strip().lower()
    if e:
        head = e.split()[0].strip("[]()").rstrip(",")
        if len(head) >= 4 and head[:5] in blob:
            return True
    return False


def register_activity(record, activity_id, migrated):
    prov = record.setdefault("_provenance", {})
    acts = prov.setdefault("activities", [])
    acts[:] = [a for a in acts if a.get("type") != ACTIVITY_TYPE]
    entry = {
        "activity_id": activity_id,
        "script": SCRIPT_NAME,
        "type": ACTIVITY_TYPE,
        "map_version": MAP_VERSION,
        "timestamp": now_iso(),
        "generated_fields": list(GENERATED_FIELDS),
    }
    if migrated:
        entry["modified_fields"] = list(MIGRATION_FIELDS)
        entry["migrated_entries"] = migrated
    acts.append(entry)


def write_atomic(path, data):
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def validate_vocabulary(spec):
    """マッピング表が産出する値が統制語彙に収まるか事前検証する."""
    cats = set(spec["categories"])
    errors = []

    def chk(d, where):
        if not isinstance(d, dict):
            return
        c, s = d.get("category"), d.get("subtype")
        if c in (None, "_delegated"):
            return
        if c not in cats:
            errors.append(f"{where}: 未知の category {c!r}")
        elif s is not None:
            if "." not in s:
                errors.append(f"{where}: subtype {s!r} が階層形式でない")
            elif s.split(".")[0] != c:
                errors.append(f"{where}: subtype {s!r} が category {c!r} と不整合")

    for k, v in spec["direct_map"].items():
        chk(v, f"direct_map[{k}]")
    for k, v in spec["multi_axis_map"].items():
        if isinstance(v, list):
            for i, d in enumerate(v):
                chk(d, f"multi_axis_map[{k}][{i}]")
    for k, v in spec["ambiguous_forms"].items():
        if not isinstance(v, dict):
            continue
        chk(v.get("default"), f"ambiguous[{k}].default")
        for i, d in enumerate(v.get("disambiguate_by_evidence", [])):
            chk(d, f"ambiguous[{k}][{i}]")
            for j, x in enumerate(d.get("multi", [])):
                chk(x, f"ambiguous[{k}][{i}].multi[{j}]")
    return errors


def main():
    ap = argparse.ArgumentParser(
        description="社会的身分カテゴリを validated_career_graphs に付与する")
    ap.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    ap.add_argument("--apply", action="store_true",
                    help="実際に書き込む（既定は dry-run）")
    ap.add_argument("--limit", type=int, help="先頭 N ファイルのみ（試走用）")
    ap.add_argument("--no-migrate", action="store_true",
                    help="career_path への移送を行わない（分類のみ）")
    ap.add_argument("--report", help="集計を JSON で書き出す")
    args = ap.parse_args()

    global MAP_VERSION
    with open(MAP_PATH, encoding="utf-8") as f:
        spec = json.load(f)
    MAP_VERSION = spec.get("version", "unknown")

    errors = validate_vocabulary(spec)
    if errors:
        print("マッピング表に統制語彙との不整合があります。中止します:",
              file=sys.stderr)
        for e in errors[:20]:
            print("  -", e, file=sys.stderr)
        return 1

    clf = Classifier(spec)
    activity_id = f"{ACTIVITY_TYPE}-v{MAP_VERSION}-rulebased-{now_compact()}"

    files = sorted(Path(args.corpus).glob("*/*/*_career.json"))
    if args.limit:
        files = files[:args.limit]
    if not files:
        print(f"対象ファイルがありません: {args.corpus}", file=sys.stderr)
        return 1

    st = collections.Counter()
    cat = collections.Counter()
    sub = collections.Counter()
    cert = collections.Counter()
    naxes = collections.Counter()
    changed_files = 0

    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[SKIP] {path.name}: {e}", file=sys.stderr)
            continue

        touched = False
        for record in data:
            hit = False
            migrated = 0
            for p in record.get("persons", []):
                kind, stmts, deleg = clf.classify(
                    p.get("social_status"), p.get("social_status_evidence"))
                st[kind] += 1
                if kind == "empty":
                    continue
                hit = True

                if kind == "delegated" or deleg:
                    val = deleg or clf.normalize(p.get("social_status"))
                    ev = (p.get("social_status_evidence") or "").strip()
                    if args.no_migrate:
                        st["移送skip(--no-migrate)"] += 1
                    elif career_mentions(p, val, ev):
                        st["career_path に既出→破棄"] += 1
                    else:
                        cp = p.setdefault("career_path", [])
                        cp.append(make_career_entry(val, ev, len(cp) + 1))
                        p["has_career"] = True
                        migrated += 1
                        st["career_path へ移送"] += 1

                if stmts:
                    p["social_statuses"] = stmts
                    naxes[len(stmts)] += 1
                    for s in stmts:
                        cat[s["category"]] += 1
                        sub[s.get("subtype") or "(none)"] += 1
                        cert[s["certainty"]] += 1
                    p["social_status_source"] = "rulebased"
                elif kind == "pending_llm":
                    p["social_status_source"] = "pending_llm"
                elif kind in ("delegated", "excluded"):
                    p["social_status_source"] = kind

            if hit:
                register_activity(record, activity_id, migrated)
                touched = True

        if touched:
            changed_files += 1
            if args.apply:
                write_atomic(path, data)

    mode = "APPLIED" if args.apply else "DRY-RUN (書き込みなし)"
    tot = sum(v for k, v in st.items()
              if k in ("empty", "excluded", "delegated", "resolved", "pending_llm"))
    print(f"=== {mode} ===")
    print(f"activity_id : {activity_id}")
    print(f"files       : {len(files)} 件中 {changed_files} 件に対象あり")
    print(f"persons     : {tot}")
    print("\n--- 処理結果 ---")
    for k in ("empty", "resolved", "delegated", "pending_llm", "excluded"):
        if st[k]:
            print(f"{st[k]:7d} {100*st[k]/tot:5.1f}%  {k}")
    print("\n--- career_path 移送 ---")
    for k in ("career_path へ移送", "career_path に既出→破棄", "移送skip(--no-migrate)"):
        if st[k]:
            print(f"{st[k]:7d}  {k}")
    print("\n--- 軸の割当て数 ---")
    for k in sorted(naxes):
        print(f"{naxes[k]:7d}  {k} 軸")
    print("\n--- category（延べ）---")
    for k, v in cat.most_common():
        print(f"{v:7d}  {k}")
    print("\n--- certainty ---")
    for k, v in cert.most_common():
        print(f"{v:7d}  {k}")
    print("\n--- subtype 上位15 ---")
    for k, v in sub.most_common(15):
        print(f"{v:7d}  {k}")

    if not args.apply:
        print("\n書き込むには --apply を付けて再実行してください。")

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump({"activity_id": activity_id, "applied": args.apply,
                       "persons": tot, "status": dict(st), "category": dict(cat),
                       "subtype": dict(sub), "certainty": dict(cert),
                       "axes": dict(naxes)}, f, ensure_ascii=False, indent=1)
        print(f"\nreport -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
