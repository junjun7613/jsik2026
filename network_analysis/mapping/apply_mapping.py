#!/usr/bin/env python3
"""寄進対象カテゴリ マッピング表の適用・検証スクリプト.

object_category_map.json のルールを validated_career_graphs に適用し、
カバレッジを集計する。--dry-run（既定）では書き出しを行わない。

仕様: network_analysis/OBJECT_TYPE_INVENTORY.md §7
"""
import argparse
import collections
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAP_PATH = HERE / "object_category_map.json"
DEFAULT_CORPUS = (
    HERE.parent.parent
    / "pipeline/provenance/validated_career_graphs/claude"
)


def load_map(path=MAP_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


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
        """(category, subtype, how, needs_llm, refine_llm) を返す.

        needs_llm  : カテゴリが決まらず LLM 判定が必須
        refine_llm : 既定カテゴリはあるが文脈次第で改善の余地あり（任意パス）
        """
        s = normalize(object_str, self.spec)
        ot = (object_type or "").strip().lower()

        # 2. 既知の多重割当形を最優先
        if s in self.ambiguous:
            a = self.ambiguous[s]
            return (a["category"], a.get("subtype"), "ambiguous",
                    a.get("needs_llm", False), a.get("refine_llm", False))

        # 3. 表層形ルール
        if s:
            for rid, pat, cat, sub in self.rules:
                if pat.search(s):
                    return cat, sub, f"surface:{rid}", False, False

        # 4. object_type フォールバック
        if ot in self.direct:
            d = self.direct[ot]
            if d.get("category"):
                return (d["category"], d.get("subtype"), "direct",
                        d.get("needs_llm", False), d.get("refine_llm", False))
            return None, None, "direct:unresolved", True, False

        # 5. 未解決
        return None, None, "unresolved", True, False


def iter_objects(corpus):
    for f in sorted(Path(corpus).glob("*/*/*_career.json")):
        try:
            data = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        for rec in data:
            for p in rec.get("persons", []):
                for b in (p.get("benefactions") or []):
                    for o in (b.get("objects") or []):
                        yield o, b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    ap.add_argument("--report", help="未解決分を JSON で書き出す")
    args = ap.parse_args()

    spec = load_map()
    clf = Classifier(spec)

    cat = collections.Counter()
    sub = collections.Counter()
    how = collections.Counter()
    llm_forms = collections.Counter()
    refine_forms = collections.Counter()
    total = 0
    needs_llm = 0
    refine_llm = 0

    for o, b in iter_objects(args.corpus):
        total += 1
        c, s, h, nl, rl = clf.classify(o.get("object"), o.get("object_type"))
        cat[c or "(unresolved)"] += 1
        sub[s or "(none)"] += 1
        how[h.split(":")[0]] += 1
        if nl:
            needs_llm += 1
            llm_forms[(o.get("object") or "")[:50]] += 1
        elif rl:
            refine_llm += 1
            refine_forms[(o.get("object") or "")[:50]] += 1

    resolved = total - needs_llm
    print(f"TOTAL objects : {total}")
    print(f"カテゴリ確定   : {resolved}  ({100*resolved/total:.1f}%)")
    print(f"  うち refine_llm 推奨: {refine_llm}  ({100*refine_llm/total:.1f}%)")
    print(f"needs_llm(必須): {needs_llm}  ({100*needs_llm/total:.1f}%)")
    print("\n--- 解決方法 ---")
    for k, v in how.most_common():
        print(f"{v:6d} {100*v/total:5.1f}%  {k}")
    print("\n--- 第1階層 category ---")
    for k, v in cat.most_common():
        print(f"{v:6d} {100*v/total:5.1f}%  {k}")
    print("\n--- 第2階層 subtype (上位25) ---")
    for k, v in sub.most_common(25):
        print(f"{v:6d} {100*v/total:5.1f}%  {k}")
    print(f"\n--- needs_llm の表層形 (distinct {len(llm_forms)}, 上位15) ---")
    for k, v in llm_forms.most_common(15):
        print(f"{v:5d}  {k}")
    print(f"\n--- refine_llm の表層形 (distinct {len(refine_forms)}, 上位10) ---")
    for k, v in refine_forms.most_common(10):
        print(f"{v:5d}  {k}")

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(
                {"total": total, "needs_llm": needs_llm, "refine_llm": refine_llm,
                 "category": dict(cat), "subtype": dict(sub),
                 "needs_llm_forms": dict(llm_forms),
                 "refine_llm_forms": dict(refine_forms)},
                f, ensure_ascii=False, indent=1)
        print(f"\nreport -> {args.report}")


if __name__ == "__main__":
    main()
