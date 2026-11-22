#!/usr/bin/env python3
"""官職の統制語彙（position_canonical / position_tier）を付与する.

network_analysis/mapping/position_canonical_map.json の規則を適用し、
career_path[] の各要素に以下を **追記** する。

    position_canonical         統制語彙（52種）。対応がなければ付与しない
    position_tier              官職の序列軸（7種）。tier_rules を持つ官職（adlectus）で
                               文脈から決まらなければ付与しない
    position_canonical_source  判定の来歴（direct / variant）
    victory_title              勝利称号の対象地域（該当時のみ）

あわせて、称号（imperator, pater patriae, 勝利称号等）の position_type を
"title" に変更する。これらは職務ではなく地位・権限・勝利称号であり、
career_path に混在していた（実測 5,693 件・27.4%）。分類も不統一で、
同じ imperator が imperial-administration 934 / military 516 /
other 3 に散っていた。

既存の position_abstract / position_normalized / position は変更しない。
抽出 LLM が生成し人手校訂の対象でもある別系統の値であり、上書きすると
生成来歴が失われるため。position_type のみ称号に限って書き換えるが、
元の値は _provenance.value_history に残す。

全659種のうち統制するのは主要な52種（89.7%）のみ。position は役職名
そのものでありローマの官職は本来多様であるため、残り609種は
position_abstract のまま残す（POSITION_INVENTORY.md §4-1）。

仕様: network_analysis/POSITION_INVENTORY.md
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
MAP_PATH = REPO_ROOT / "network_analysis/mapping/position_canonical_map.json"
DEFAULT_CORPUS = SCRIPT_DIR / "validated_career_graphs" / "claude"

SCRIPT_NAME = "classify_position.py"
ACTIVITY_TYPE = "classify_position"
GENERATED_FIELDS = [
    "career_path[].position_canonical",
    "career_path[].position_tier",
    "career_path[].position_canonical_source",
    "career_path[].victory_title",
]
MODIFIED_FIELDS = ["career_path[].position_type"]


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_compact():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")


class Classifier:
    def __init__(self, spec):
        self.titles = {k: v for k, v in spec["titles"].items()
                       if not k.startswith("$")}
        self.offices = {k: v for k, v in spec["offices"].items()
                        if not k.startswith("$")}
        self.variants = spec["normalize"]["explicit_variants"]
        # tier が編入先などの文脈で決まる官職（v1.1 で adlectus に導入）
        self.tier_rules = {
            k: [(re.compile(r["pattern"], re.IGNORECASE), r["tier"],
                 r.get("unless_position_type", {})) for r in v["tier_rules"]]
            for k, v in self.offices.items() if v.get("tier_rules")}
        # 小文字化による一括統合は行わない。medicus（医師）と
        # Medicus（勝利称号）が同綴異義のため（POSITION_INVENTORY.md §3-3）
        assert spec["normalize"]["case_insensitive"] is False

    def contextual_tier(self, canonical_key, entry, context):
        """tier_rules を持つ官職の tier を文脈から決める。決まらなければ None.

        context は career_path の要素。position_normalized と position
        （抽出時の表記）を照合し、上から順に最初に一致した規則を採る。
        """
        text = " ".join(filter(None, [(context or {}).get("position_normalized"),
                                       (context or {}).get("position")]))
        ptype = (context or {}).get("position_type")
        for pattern, tier, unless in self.tier_rules[canonical_key]:
            if pattern.search(text):
                return unless.get(ptype, tier)
        return entry.get("tier_fallback_by_position_type", {}).get(ptype)

    def classify(self, abstract, context=None):
        """(canonical, tier, is_title, victory, source) を返す。
        統制対象外なら canonical が None。tier_rules を持つ官職で文脈から
        tier が決まらない場合、tier は None."""
        a = (abstract or "").strip()
        if not a:
            return None, None, False, None, None

        source = "direct"
        if a in self.variants and a not in self.titles and a not in self.offices:
            a = self.variants[a]
            source = "variant"

        e = self.titles.get(a)
        if e:
            # 表記ゆれ経由で来た場合も variant と記録する
            src = source if source == "variant" else (
                "variant" if e.get("note") == "表記ゆれ" else "direct")
            return e["canonical"], e["tier"], True, e.get("victory"), src

        e = self.offices.get(a)
        if e:
            src = source if source == "variant" else (
                "variant" if e.get("note", "").endswith("別表記") else "direct")
            tier = (self.contextual_tier(a, e, context) if a in self.tier_rules
                    else e["tier"])
            return e["canonical"], tier, False, None, src

        return None, None, False, None, None


def validate_map(spec):
    """マップが産出する値が宣言した tier に収まるか事前検証する."""
    tiers = {k for k in spec["tiers"] if not k.startswith("$")}
    errors = []
    for section in ("titles", "offices"):
        for k, v in spec[section].items():
            if k.startswith("$"):
                continue
            if not v.get("canonical"):
                errors.append(f"{section}[{k}]: canonical がありません")
            if v.get("tier_rules"):
                produced = [r.get("tier") for r in v["tier_rules"]]
                produced += [t for r in v["tier_rules"]
                             for t in r.get("unless_position_type", {}).values()]
                produced += list(v.get("tier_fallback_by_position_type", {}).values())
                for t in produced:
                    if t not in tiers:
                        errors.append(f"{section}[{k}]: tier_rules に未知の tier {t!r}")
                for r in v["tier_rules"]:
                    try:
                        re.compile(r["pattern"])
                    except re.error as e:
                        errors.append(f"{section}[{k}]: 不正な pattern {r['pattern']!r}: {e}")
            elif v.get("tier") not in tiers:
                errors.append(f"{section}[{k}]: 未知の tier {v.get('tier')!r}")
    return errors


def register_activity(record, activity_id, map_version, retyped):
    prov = record.setdefault("_provenance", {})
    acts = prov.setdefault("activities", [])
    acts[:] = [a for a in acts if a.get("type") != ACTIVITY_TYPE]
    entry = {
        "activity_id": activity_id,
        "script": SCRIPT_NAME,
        "type": ACTIVITY_TYPE,
        "map_version": map_version,
        "timestamp": now_iso(),
        "generated_fields": list(GENERATED_FIELDS),
    }
    if retyped:
        entry["modified_fields"] = list(MODIFIED_FIELDS)
        entry["retyped_to_title"] = retyped
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


def main():
    ap = argparse.ArgumentParser(
        description="官職の統制語彙を validated_career_graphs に付与する")
    ap.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    ap.add_argument("--apply", action="store_true",
                    help="実際に書き込む（既定は dry-run）")
    ap.add_argument("--limit", type=int, help="先頭 N ファイルのみ（試走用）")
    ap.add_argument("--no-retype", action="store_true",
                    help="称号の position_type 変更を行わない（付与のみ）")
    ap.add_argument("--report", help="集計を JSON で書き出す")
    args = ap.parse_args()

    with open(MAP_PATH, encoding="utf-8") as f:
        spec = json.load(f)
    errors = validate_map(spec)
    if errors:
        print("マッピング表に不整合があります。中止します:", file=sys.stderr)
        for e in errors[:20]:
            print("  -", e, file=sys.stderr)
        return 1

    clf = Classifier(spec)
    map_version = spec.get("version", "unknown")
    activity_id = f"{ACTIVITY_TYPE}-v{map_version}-rulebased-{now_compact()}"

    files = sorted(Path(args.corpus).glob("*/*/*_career.json"))
    if args.limit:
        files = files[:args.limit]
    if not files:
        print(f"対象ファイルがありません: {args.corpus}", file=sys.stderr)
        return 1

    st = collections.Counter()
    canon = collections.Counter()
    tier = collections.Counter()
    oldtype = collections.Counter()
    tier_changes = collections.Counter()
    changed_files = 0

    try:
        from _provenance_utils import record_superseded_value
    except ImportError:
        record_superseded_value = None

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
            retyped = 0
            for pi, person in enumerate(record.get("persons", [])):
                for ci, c in enumerate(person.get("career_path") or []):
                    st["total"] += 1
                    cn, tr, is_title, victory, src = clf.classify(
                        c.get("position_abstract"), context=c)
                    if cn is None:
                        st["uncontrolled"] += 1
                        continue

                    # 前回の分類結果から tier が変わる場合は旧値を履歴に残す
                    old_tier = c.get("position_tier")
                    if old_tier is not None and old_tier != tr:
                        tier_changes[(cn, old_tier, tr)] += 1
                        if record_superseded_value:
                            record_superseded_value(
                                record,
                                path=f"person/{pi}.career_path[{ci}].position_tier",
                                field_label="career_path[].position_tier",
                                old_value=old_tier,
                                superseded_by={"activity_id": activity_id},
                                superseded_at=now_iso())

                    c["position_canonical"] = cn
                    if tr is None:
                        c.pop("position_tier", None)
                        st["tier_unresolved"] += 1
                    else:
                        c["position_tier"] = tr
                        tier[tr] += 1
                    c["position_canonical_source"] = src
                    if victory:
                        c["victory_title"] = victory
                    canon[cn] += 1
                    st["controlled"] += 1
                    hit = True

                    if is_title and not args.no_retype:
                        old = c.get("position_type")
                        if old != "title":
                            oldtype[old] += 1
                            # 書き換える前の値を履歴に残す。career_path は
                            # Statement として _vN 版を持つが、JSON 上は
                            # 同じキーに代入されるため元の値が消える。
                            if record_superseded_value:
                                record_superseded_value(
                                    record,
                                    path=f"person/{pi}.career_path[{ci}].position_type",
                                    field_label="career_path[].position_type",
                                    old_value=old,
                                    superseded_by={"activity_id": activity_id},
                                    superseded_at=now_iso())
                            c["position_type"] = "title"
                            retyped += 1
                            st["retyped_to_title"] += 1

            if hit:
                register_activity(record, activity_id, map_version, retyped)
                touched = True

        if touched:
            changed_files += 1
            if args.apply:
                write_atomic(path, data)

    mode = "APPLIED" if args.apply else "DRY-RUN (書き込みなし)"
    tot = st["total"]
    print(f"=== {mode} ===")
    print(f"activity_id : {activity_id}")
    print(f"files       : {len(files)} 件中 {changed_files} 件に対象あり")
    print(f"career_path : {tot}")
    if tot:
        print(f"  統制語彙を付与 : {st['controlled']} ({100*st['controlled']/tot:.1f}%)")
        print(f"  統制対象外     : {st['uncontrolled']} ({100*st['uncontrolled']/tot:.1f}%)")
        print(f"  title に変更   : {st['retyped_to_title']}")
    if oldtype:
        print("\n--- title へ変更した元の position_type ---")
        for k, v in oldtype.most_common():
            print(f"{v:7d}  {k}")
    if tier_changes:
        print("\n--- 前回から tier が変わるもの (canonical: 旧 → 新) ---")
        for (cn, o, n), v in tier_changes.most_common():
            print(f"{v:7d}  {cn}: {o} → {n or '（付与しない）'}")
    if st["tier_unresolved"]:
        print(f"\n文脈から tier が決まらず付与しないもの: {st['tier_unresolved']}")
    print("\n--- tier 別 ---")
    for k, v in tier.most_common():
        print(f"{v:7d}  {k}")
    print("\n--- canonical 上位15 ---")
    for k, v in canon.most_common(15):
        print(f"{v:7d}  {k}")

    if not args.apply:
        print("\n書き込むには --apply を付けて再実行してください。")

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump({"activity_id": activity_id, "applied": args.apply,
                       "stats": dict(st), "canonical": dict(canon),
                       "tier": dict(tier), "retyped_from": dict(oldtype),
                       "tier_changes": [{"canonical": c, "from": o, "to": n, "count": v}
                                        for (c, o, n), v in tier_changes.most_common()]},
                      f, ensure_ascii=False, indent=1)
        print(f"\nreport -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
