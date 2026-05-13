#!/usr/bin/env python3
"""
Evaluate career_graphs social_status against EDH using status_mapping.json.

Input:
  ../name_components/name_eval_result_claude.json  (aligned person pairs)
  status_mapping.json                              (CG/EDH → canonical mapping)

Output:
  status_eval_result.txt
"""

import json
from pathlib import Path
from collections import defaultdict

DIR        = Path(__file__).parent
PAIRS_JSON = DIR.parent / 'name_components' / 'name_eval_result_claude.json'
MAPPING    = DIR / 'status_mapping.json'
OUTPUT     = DIR / 'status_eval_result.txt'


def build_lookup(mapping: dict) -> dict[str, str]:
    """{ cg_or_edh_value → canonical_edh_category }"""
    lookup = {}
    for canonical, aliases in mapping.items():
        if canonical.startswith('_'):
            continue
        lookup[canonical] = canonical
        for alias in aliases:
            lookup[alias.lower()] = canonical
    return lookup


def normalize(value: str, lookup: dict) -> str | None:
    """Returns canonical category, or None if unmappable."""
    v = (value or '').strip().lower()
    # try as-is, then with underscores→hyphens, then hyphens→underscores
    return lookup.get(v) or lookup.get(v.replace('_', '-')) or lookup.get(v.replace('-', '_'))


def main():
    mapping = json.loads(MAPPING.read_text(encoding='utf-8'))
    lookup  = build_lookup(mapping)

    data    = json.loads(PAIRS_JSON.read_text(encoding='utf-8'))
    pairs   = [p for r in data['results'] for p in r['pairs'] if p.get('aligned')]

    tp = defaultdict(int)  # True Positive per category
    fp = defaultdict(int)  # False Positive (CG wrong)
    fn = defaultdict(int)  # False Negative (EDH has value, CG missing/wrong)

    total = skipped = both_missing = 0

    for p in pairs:
        total += 1
        edh_norm = normalize(p.get('edh_status', ''), lookup)
        cg_norm  = normalize(p.get('cg_status',  ''), lookup)

        if edh_norm is None and cg_norm is None:
            both_missing += 1
            continue

        if edh_norm is None:
            # EDH 未記載・マッピング外 → 評価不能
            skipped += 1
            continue

        # EDH に値あり
        if cg_norm == edh_norm:
            tp[edh_norm] += 1
        else:
            fn[edh_norm] += 1
            if cg_norm is not None:
                fp[cg_norm] += 1

    # 集計
    categories = sorted(set(list(tp) + list(fp) + list(fn)))
    total_tp = sum(tp.values())
    total_fp = sum(fp.values())
    total_fn = sum(fn.values())

    def prf(t, f_p, f_n):
        p = t / (t + f_p) if (t + f_p) else 0
        r = t / (t + f_n) if (t + f_n) else 0
        f = 2 * p * r / (p + r) if (p + r) else 0
        return p, r, f

    lines = []
    lines.append('=== Social Status Evaluation ===')
    lines.append(f'Aligned pairs total : {total:,}')
    lines.append(f'Both missing/unmappable: {both_missing:,}')
    lines.append(f'EDH unmappable (skipped): {skipped:,}')
    lines.append(f'Evaluated pairs     : {total - both_missing - skipped:,}')
    lines.append('')

    lines.append(f'{"Category":<22} {"TP":>5} {"FP":>5} {"FN":>5}  {"Prec":>7} {"Rec":>7} {"F1":>7}')
    lines.append('-' * 62)
    for cat in categories:
        t, fp_, fn_ = tp[cat], fp[cat], fn[cat]
        pr, rc, f1 = prf(t, fp_, fn_)
        lines.append(f'{cat:<22} {t:>5} {fp_:>5} {fn_:>5}  {pr:>7.1%} {rc:>7.1%} {f1:>7.1%}')

    lines.append('-' * 62)

    # マイクロ平均
    p_micro, r_micro, f1_micro = prf(total_tp, total_fp, total_fn)
    lines.append(f'{"MICRO avg":<22} {total_tp:>5} {total_fp:>5} {total_fn:>5}  {p_micro:>7.1%} {r_micro:>7.1%} {f1_micro:>7.1%}')

    # マクロ平均（カテゴリ均等）
    cat_prf = [prf(tp[c], fp[c], fn[c]) for c in categories]
    p_macro  = sum(x[0] for x in cat_prf) / len(cat_prf)
    r_macro  = sum(x[1] for x in cat_prf) / len(cat_prf)
    f1_macro = sum(x[2] for x in cat_prf) / len(cat_prf)
    lines.append(f'{"MACRO avg":<22} {"":>5} {"":>5} {"":>5}  {p_macro:>7.1%} {r_macro:>7.1%} {f1_macro:>7.1%}')

    # 件数加重マクロ平均（TP+FN = EDH側の実件数で重みづけ）
    weights = [tp[c] + fn[c] for c in categories]
    total_w = sum(weights)
    p_wmacro  = sum(w * x[0] for w, x in zip(weights, cat_prf)) / total_w if total_w else 0
    r_wmacro  = sum(w * x[1] for w, x in zip(weights, cat_prf)) / total_w if total_w else 0
    f1_wmacro = sum(w * x[2] for w, x in zip(weights, cat_prf)) / total_w if total_w else 0
    lines.append(f'{"WEIGHTED MACRO avg":<22} {"":>5} {"":>5} {"":>5}  {p_wmacro:>7.1%} {r_wmacro:>7.1%} {f1_wmacro:>7.1%}')

    output = '\n'.join(lines)
    print(output)
    OUTPUT.write_text(output + '\n', encoding='utf-8')
    print(f'\nSaved → {OUTPUT}')


if __name__ == '__main__':
    main()
