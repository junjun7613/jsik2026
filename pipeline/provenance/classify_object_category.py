#!/usr/bin/env python3
"""寄進対象カテゴリ（2階層統制語彙）を validated_career_graphs に付与する.

network_analysis/mapping/object_category_map.json の規則を適用し、
benefactions[].objects[] の各要素に以下の3フィールドを **追記** する。

    object_category        第1階層（9種）。確定できない場合は付与しない
    object_subtype         第2階層。確定できない場合は付与しない
    object_category_source 判定の来歴（surface:<id> / ambiguous / direct / pending_llm）

既存の object / object_type は変更しない。object_type は抽出 LLM が生成し
人手校訂の対象でもある別系統の値であり、本スクリプトの出力で上書きすると
生成来歴が失われるため。両者は RDF 上でも別プロパティに対応する
（epig:objectType と epig:objectCategory）。

入力は objects[] 配列とする。benefaction 直下のスカラー object_type とは
15.2% で食い違うが、その大半（building→tomb 382, other→altar 162 など）は
enrich が objects[] を生成する際に再判定した結果であり、objects[] 側が
精緻化後の値であるため。

カテゴリが確定しなかった要素には object_category を付けず、
object_category_source="pending_llm" のみを記録する。LLM 分類パス
（Phase 3）が後からこの印を頼りに対象を絞れるようにするため。

仕様: network_analysis/OBJECT_TYPE_INVENTORY.md §7
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
MAP_PATH = REPO_ROOT / "network_analysis/mapping/object_category_map.json"
DEFAULT_CORPUS = SCRIPT_DIR / "validated_career_graphs" / "claude"

SCRIPT_NAME = "classify_object_category.py"
ACTIVITY_TYPE = "classify_object_category"
GENERATED_FIELDS = [
    "benefactions[].objects[].object_category",
    "benefactions[].objects[].object_subtype",
    "benefactions[].objects[].object_category_source",
]


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")


# ── 分類器（network_analysis/mapping/apply_mapping.py と同一ロジック） ──────────

def normalize(s, spec):
    """翻刻記号・正書法のゆれを除去する."""
    s = (s or "").strip().lower()
    # <u=I> 形式は『正しい読み=刻まれた字』。左辺を採用
    ec = spec["normalize_surface"]["expand_correction"]
    s = re.sub(ec["pattern"], lambda m: m.group(1), s)
    s = re.sub(r"\(([^)]*)\)", r"\1", s)   # fec(it) -> fecit
    s = re.sub(r"\[([^\]]*)\]", r"\1", s)  # [miliari]a -> miliaria
    s = re.sub(r"[!?]+$", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


class Classifier:
    def __init__(self, spec):
        self.spec = spec
        self.ambiguous = spec["ambiguous_forms"]
        self.rules = [
            (r["id"], re.compile(r["pattern"]), r["category"], r["subtype"])
            for r in spec["surface_rules"]
            if "pattern" in r
        ]
        self.direct = spec["object_type_direct"]

    def classify(self, object_str, object_type):
        """(category, subtype, how, needs_llm, refine_llm) を返す."""
        s = normalize(object_str, self.spec)
        ot = (object_type or "").strip().lower()

        if s in self.ambiguous:
            a = self.ambiguous[s]
            return (a["category"], a.get("subtype"), "ambiguous",
                    a.get("needs_llm", False), a.get("refine_llm", False))

        if s:
            for rid, pat, cat, sub in self.rules:
                if pat.search(s):
                    return cat, sub, f"surface:{rid}", False, False

        if ot in self.direct:
            d = self.direct[ot]
            if d.get("category"):
                return (d["category"], d.get("subtype"), "direct",
                        d.get("needs_llm", False), d.get("refine_llm", False))
            return None, None, "direct:unresolved", True, False

        return None, None, "unresolved", True, False


# ── 整合性チェック ────────────────────────────────────────────────────────────

def validate_vocabulary(spec):
    """マッピング表が産出しうる値が統制語彙の範囲に収まるか事前検証する.

    データを書き換えてから語彙の不整合に気付くと巻き戻しが要るため、
    1件も書き込む前に確認する。
    """
    cats = set(spec["categories"])
    errors = []

    def check(cat, sub, where):
        if cat is not None and cat not in cats:
            errors.append(f"{where}: 未知の category {cat!r}")
        if sub is not None:
            if "." not in sub:
                errors.append(f"{where}: subtype {sub!r} が階層形式でない")
            elif sub.split(".")[0] != cat:
                errors.append(f"{where}: subtype {sub!r} が category {cat!r} と不整合")

    # マッピング表は $comment キーを各所に混在させているため dict のみ見る
    for form, a in spec["ambiguous_forms"].items():
        if isinstance(a, dict):
            check(a.get("category"), a.get("subtype"), f"ambiguous_forms[{form!r}]")
    for r in spec["surface_rules"]:
        if isinstance(r, dict) and "pattern" in r:
            check(r.get("category"), r.get("subtype"), f"surface_rules[{r.get('id')}]")
    for ot, d in spec["object_type_direct"].items():
        if isinstance(d, dict):
            check(d.get("category"), d.get("subtype"), f"object_type_direct[{ot!r}]")
    return errors


# ── 適用 ──────────────────────────────────────────────────────────────────────

def iter_objects(record):
    for p in record.get("persons", []):
        for b in (p.get("benefactions") or []):
            for o in (b.get("objects") or []):
                yield o


def register_activity(record, activity_id):
    """_provenance.activities に本パスを登録する.

    create_rdf_himiko.py は generated_fields にフィールドパスが載っている
    活動しか参照しないため、ここで登録しないと RDF 化時に無視される。
    再実行時は同一 activity_id で上書きし、重複登録を避ける。
    """
    prov = record.setdefault("_provenance", {})
    acts = prov.setdefault("activities", [])
    acts[:] = [a for a in acts if a.get("type") != ACTIVITY_TYPE]
    acts.append({
        "activity_id": activity_id,
        "script": SCRIPT_NAME,
        "type": ACTIVITY_TYPE,
        "map_version": MAP_VERSION,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_fields": list(GENERATED_FIELDS),
    })


def write_atomic(path, data):
    """同一ディレクトリの一時ファイルに書いてから置換する.

    書き込み途中で中断してもファイルが壊れないようにするため。
    対象が最大 68MB と大きく、全件で 524MB あるため部分書き込みの
    リスクを無視できない。
    """
    d = path.parent
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp_", suffix=".json")
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
        description="寄進対象カテゴリを validated_career_graphs に付与する")
    ap.add_argument("--corpus", default=str(DEFAULT_CORPUS),
                    help="対象ディレクトリ（既定: validated_career_graphs/claude）")
    ap.add_argument("--apply", action="store_true",
                    help="実際に書き込む（既定は dry-run で一切書き込まない）")
    ap.add_argument("--limit", type=int,
                    help="先頭 N ファイルのみ処理（試走用）")
    ap.add_argument("--report", help="集計結果を JSON で書き出す")
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
    activity_id = f"{ACTIVITY_TYPE}-v{MAP_VERSION}-rulebased-{now_iso()}"

    files = sorted(Path(args.corpus).glob("*/*/*_career.json"))
    if args.limit:
        files = files[:args.limit]
    if not files:
        print(f"対象ファイルがありません: {args.corpus}", file=sys.stderr)
        return 1

    cat = collections.Counter()
    sub = collections.Counter()
    how = collections.Counter()
    total = pending = refine = 0
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
            for o in iter_objects(record):
                total += 1
                c, s, h, nl, rl = clf.classify(o.get("object"),
                                               o.get("object_type"))
                cat[c or "(unresolved)"] += 1
                sub[s or "(none)"] += 1
                how[h.split(":")[0]] += 1

                if nl:
                    pending += 1
                    # カテゴリ未確定。確定値は書かず、印だけ残して
                    # LLM パスが対象を絞れるようにする
                    o.pop("object_category", None)
                    o.pop("object_subtype", None)
                    o["object_category_source"] = "pending_llm"
                else:
                    if rl:
                        refine += 1
                    o["object_category"] = c
                    if s:
                        o["object_subtype"] = s
                    else:
                        o.pop("object_subtype", None)
                    o["object_category_source"] = h
                hit = True
            if hit:
                register_activity(record, activity_id)
                touched = True

        if touched:
            changed_files += 1
            if args.apply:
                write_atomic(path, data)

    mode = "APPLIED" if args.apply else "DRY-RUN (書き込みなし)"
    resolved = total - pending
    print(f"=== {mode} ===")
    print(f"activity_id : {activity_id}")
    print(f"files       : {len(files)} 件中 {changed_files} 件に対象あり")
    print(f"objects     : {total}")
    if total:
        print(f"  カテゴリ確定 : {resolved} ({100*resolved/total:.1f}%)")
        print(f"    うち refine_llm 推奨 : {refine} ({100*refine/total:.1f}%)")
        print(f"  pending_llm  : {pending} ({100*pending/total:.1f}%)")
    print("\n--- 解決方法 ---")
    for k, v in how.most_common():
        print(f"{v:6d} {100*v/total:5.1f}%  {k}")
    print("\n--- 第1階層 category ---")
    for k, v in cat.most_common():
        print(f"{v:6d} {100*v/total:5.1f}%  {k}")
    print("\n--- 第2階層 subtype (上位20) ---")
    for k, v in sub.most_common(20):
        print(f"{v:6d} {100*v/total:5.1f}%  {k}")

    if not args.apply:
        print("\n書き込むには --apply を付けて再実行してください。")

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump({"activity_id": activity_id, "applied": args.apply,
                       "total": total, "resolved": resolved,
                       "pending_llm": pending, "refine_llm": refine,
                       "category": dict(cat), "subtype": dict(sub),
                       "how": dict(how)}, f, ensure_ascii=False, indent=1)
        print(f"\nreport -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
