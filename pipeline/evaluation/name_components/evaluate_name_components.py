#!/usr/bin/env python3
"""
Evaluate career_graphs name components (praenomen/nomen/cognomen/gender/social_status)
against EDH parsed data.

Pipeline:
  1. Load edh_people_parsed.csv  → EDH persons keyed by HD number
  2. Load HD→EDCS cache (hd_to_edcs_cache.json)
     For uncached HD numbers: call TexRelations API (HD→EDCS)
  3. For each HD in target provinces, find matching career_graph record by EDCS-ID
  4. Align EDH persons ↔ CG persons by best name token overlap
  5. Compare praenomen / nomen / cognomen / gender / social_status

Output:
  evaluation/name_eval_result_<model>.json
  evaluation/name_eval_summary_<model>.txt

Usage:
    python evaluation/evaluate_name_components.py --model claude
    python evaluation/evaluate_name_components.py --model claude --no-api
    python evaluation/evaluate_name_components.py --model claude --provinces "Africa Proconsularis"
"""

import json
import csv
import re
import time
import argparse
from pathlib import Path
from collections import defaultdict

import requests

EVAL_DIR     = Path(__file__).parent
PIPELINE_DIR = EVAL_DIR.parent.parent
CAREER_DIR   = PIPELINE_DIR / 'provenance' / 'career_graphs'
LINKED_DIR   = EVAL_DIR / 'edh_linked_data'
PEOPLE_CSV   = LINKED_DIR / 'edh_people_parsed.csv'
INSCR_CSV    = LINKED_DIR / 'edh_inscriptions.csv'
CACHE_PATH   = EVAL_DIR / 'hd_to_edcs_cache.json'

TEXRELATIONS  = 'https://www.trismegistos.org/dataservices/texrelations/{id}?source=edh'
CORRESP_CSV   = EVAL_DIR / 'EDH_EDCS_corresp.csv'

DEFAULT_PROVINCES = ['Africa Proconsularis', 'Numidia']

# Praenomen normalization: abbreviation ↔ full form
PRAENOMEN_NORM = {
    'a': 'aulus',    'c': 'gaius',    'cn': 'gnaeus',  'd': 'decimus',
    'k': 'kaeso',    'l': 'lucius',   'm': 'marcus',   "m'": 'manius',
    'n': 'numerius', 'p': 'publius',  'q': 'quintus',  'ser': 'servius',
    'sex': 'sextus', 'sp': 'spurius', 't': 'titus',    'ti': 'tiberius',
    'v': 'vibius',
    # Alternate spellings found in CG output
    'caius': 'gaius',
}

def _norm_praenomen(s: str) -> str:
    s = re.sub(r'[^a-z\'.]', '', (s or '').lower()).rstrip('.')
    return PRAENOMEN_NORM.get(s, s)


# Map EDH/CG social_status values to canonical groups
STATUS_ALIASES = {
    'senatorial':       {'senatorial', 'senator', 'senator-clarissimus', 'clarissimus',
                         'senatorial order'},
    'equestrian':       {'equestrian', 'eques', 'equestrian order'},
    'decurial':         {'decurial', 'decurion', 'decurio', 'municipal-magistrate',
                         'local-magistrate', 'ordo decurionum'},
    'military':         {'military', 'soldier', 'veteran', 'miles', 'officer',
                         'miles gregarius', 'centurion', 'tribunus'},
    'imperial_household': {'imperial_household', 'imperial household', 'emperor',
                           'augustus', 'caesar', 'imperial family'},
    'freedman':         {'freedman', 'freedwoman', 'libertus', 'liberta',
                         'freedperson', 'freed'},
    'slave':            {'slave', 'servus', 'serva', 'servile'},
    'augustalis':       {'augustalis', 'sevir augustalis', 'sevir'},
    'local_official':   {'local_official', 'local official', 'lower_local_officials'},
    'foreign_ruler':    {'foreign_ruler'},
}

def _status_group(s: str) -> str:
    s = (s or '').lower().strip().replace('_', ' ')
    for canonical, aliases in STATUS_ALIASES.items():
        norm_canonical = canonical.replace('_', ' ')
        if s == norm_canonical or s == canonical or s in aliases:
            return canonical
    return s


# ── Load HD→EDCS correspondence table ────────────────────────────────────────

def load_corresp() -> dict:
    """
    Read EDH_EDCS_corresp.csv.
    Returns { hd_number: [edcs_id, ...] }
    EDCS column may contain multiple comma-separated IDs — all are included.
    """
    if not CORRESP_CSV.exists():
        return {}
    corresp = {}
    with open(CORRESP_CSV, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            edh_num  = row.get('EDH', '').strip().strip('"')
            edcs_val = row.get('EDCS', '').strip().strip('"')
            if not edh_num:
                continue
            hd = f"HD{edh_num.zfill(6)}"
            ids = []
            for part in edcs_val.split(','):
                part = part.strip()
                if part:
                    ids.append(f"EDCS-{part.zfill(8)}")
            corresp[hd] = ids  # empty list if EDCS was blank
    print(f'Corresp table: {len(corresp)} HD entries '
          f'({sum(1 for v in corresp.values() if v)} with EDCS)')
    return corresp


# ── Load EDH data ─────────────────────────────────────────────────────────────

def load_edh(provinces: list[str]) -> dict:
    """{ hd_number: [ {name, parsed_praenomen, parsed_nomen, parsed_cognomen, gender, social_status, ...} ] }"""
    hd_province = {}
    with open(INSCR_CSV, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            hd_province[row['hd_number']] = row['province_name']

    target = set(provinces)
    edh = defaultdict(list)
    with open(PEOPLE_CSV, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            hd = row['hd_number']
            if hd_province.get(hd, '') not in target:
                continue
            edh[hd].append(row)

    total = sum(len(v) for v in edh.values())
    print(f'EDH: {total:,} persons across {len(edh):,} inscriptions ({", ".join(provinces)})')
    return dict(edh)


# ── Career graphs index ───────────────────────────────────────────────────────

def build_cg_index(model_dir: Path) -> dict:
    """{ edcs_id: record }"""
    index = {}
    for entry in sorted(model_dir.iterdir()):
        if not entry.is_dir():
            continue
        subdirs = [entry] if any(entry.glob('*.json')) else [
            s for s in sorted(entry.iterdir()) if s.is_dir()
        ]
        for place_dir in subdirs:
            for json_path in sorted(place_dir.glob('*.json')):
                try:
                    for rec in json.loads(json_path.read_text(encoding='utf-8')):
                        eid = rec.get('edcs_id', '')
                        if eid:
                            index[eid] = rec
                except Exception:
                    continue
    print(f'Career graph index: {len(index):,} records')
    return index


# ── HD → EDCS ────────────────────────────────────────────────────────────────

def load_cache() -> dict:
    return json.loads(CACHE_PATH.read_text(encoding='utf-8')) if CACHE_PATH.exists() else {}

def save_cache(cache: dict):
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding='utf-8')

def hd_to_edcs(hd: str, session: requests.Session, cache: dict, sleep: float) -> str | None:
    if hd in cache:
        return cache[hd]
    url = TEXRELATIONS.format(id=hd)
    try:
        r = session.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get('EDCS'):
                    raw = item['EDCS'][0] if isinstance(item['EDCS'], list) else item['EDCS']
                    edcs_id = f"EDCS-{str(raw).zfill(8)}"
                    cache[hd] = edcs_id
                    return edcs_id
        cache[hd] = None
        return None
    except Exception:
        return None
    finally:
        time.sleep(sleep)


# ── Name comparison helpers ───────────────────────────────────────────────────

def _norm(s: str) -> str:
    return re.sub(r'[^a-z]', '', (s or '').lower())

def token_overlap(a: str, b: str) -> float:
    sa = set(re.sub(r'[^a-z]', ' ', (a or '').lower()).split())
    sb = set(re.sub(r'[^a-z]', ' ', (b or '').lower()).split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(len(sa), len(sb))

def field_match(edh_val: str, cg_val: str, field: str = '') -> str:
    """Returns 'match', 'mismatch', or 'missing' (when either is empty)."""
    if field == 'praenomen':
        a = _norm_praenomen(edh_val)
        b = _norm_praenomen(cg_val)
    else:
        a = _norm(edh_val)
        b = _norm(cg_val)
    if not a or not b:
        return 'missing'
    return 'match' if a == b else 'mismatch'

def field_match_status(edh_val: str, cg_val: str) -> str:
    a = _status_group(edh_val)
    b = _status_group(cg_val)
    if not a or not b:
        return 'missing'
    return 'match' if a == b else 'mismatch'


# ── Align persons ─────────────────────────────────────────────────────────────

def align_persons(edh_persons: list, cg_persons: list) -> tuple[list[dict], list[dict]]:
    """
    Greedy 1-to-1 alignment: pair each EDH person with the highest-scoring
    available CG person; once a CG person is used it cannot be reused.
    Returns (pairs, unmatched_cg):
      - pairs: list of aligned EDH↔CG comparison dicts (one per EDH person)
      - unmatched_cg: CG persons that were not matched to any EDH person
    """
    # Build all (score, edh_idx, cg_idx) candidates sorted by score descending
    candidates = sorted(
        (
            (token_overlap(ep.get('name', ''), cp.get('person_name', '')), i, j)
            for i, ep in enumerate(edh_persons)
            for j, cp in enumerate(cg_persons)
        ),
        key=lambda x: -x[0],
    )

    used_edh: set[int] = set()
    used_cg_indices: set[int] = set()
    edh_to_cg: dict[int, tuple[int, float]] = {}  # edh_idx → (cg_idx, score)

    for score, i, j in candidates:
        if i in used_edh or j in used_cg_indices:
            continue
        edh_to_cg[i] = (j, score)
        used_edh.add(i)
        used_cg_indices.add(j)
        if len(used_edh) == len(edh_persons):
            break

    pairs = []
    for i, ep in enumerate(edh_persons):
        edh_full = ep.get('name', '')
        if i in edh_to_cg:
            best_idx, best_score = edh_to_cg[i]
            cp = cg_persons[best_idx]
        else:
            best_idx, best_score = -1, 0.0
            cp = {}
        aligned = best_score > 0.0
        # Only compare name components when the alignment is reliable
        # (name_overlap=0 means praenomen-only match: too weak for field comparison)
        aligned = best_score > 0.0

        pairs.append({
            # EDH side
            'edh_name':      edh_full,
            'edh_praenomen': ep.get('parsed_praenomen', ''),
            'edh_nomen':     ep.get('parsed_nomen', ''),
            'edh_cognomen':  ep.get('parsed_cognomen', ''),
            'edh_gender':    ep.get('gender', ''),
            'edh_status':    ep.get('social_status', ''),
            'edh_conf':      ep.get('parse_confidence', ''),
            # CG side
            'cg_name':       cp.get('person_name', '') if cp else '',
            'cg_praenomen':  cp.get('praenomen', '')   if cp else '',
            'cg_nomen':      cp.get('nomen', '')       if cp else '',
            'cg_cognomen':   cp.get('cognomen', '')    if cp else '',
            'cg_gender':     cp.get('gender', '')      if cp else '',
            'cg_status':     cp.get('social_status', '') if cp else '',
            # Scores
            'name_overlap':  round(best_score, 3),
            'aligned':       aligned,
            'm_praenomen':   field_match(ep.get('parsed_praenomen', ''), cp.get('praenomen', '') if cp else '', 'praenomen') if aligned else 'missing',
            'm_nomen':       field_match(ep.get('parsed_nomen', ''),     cp.get('nomen', '')     if cp else '') if aligned else 'missing',
            'm_cognomen':    field_match(ep.get('parsed_cognomen', ''),  cp.get('cognomen', '')  if cp else '') if aligned else 'missing',
            'm_gender':      field_match(ep.get('gender', ''),           cp.get('gender', '')    if cp else '') if aligned else 'missing',
            'm_status':      field_match_status(ep.get('social_status', ''), cp.get('social_status', '') if cp else '') if aligned else 'missing',
        })

    # CG persons not matched to any EDH person
    unmatched_cg = [
        {
            'cg_name':      cp.get('person_name', ''),
            'cg_praenomen': cp.get('praenomen', ''),
            'cg_nomen':     cp.get('nomen', ''),
            'cg_cognomen':  cp.get('cognomen', ''),
            'cg_gender':    cp.get('gender', ''),
            'cg_status':    cp.get('social_status', ''),
        }
        for j, cp in enumerate(cg_persons)
        if j not in used_cg_indices
    ]

    return pairs, unmatched_cg


# ── Summary helpers ───────────────────────────────────────────────────────────

def rate(pairs: list[dict], field: str) -> dict:
    matched   = sum(1 for p in pairs if p[field] == 'match')
    mismatched = sum(1 for p in pairs if p[field] == 'mismatch')
    missing   = sum(1 for p in pairs if p[field] == 'missing')
    total     = len(pairs)
    comparable = matched + mismatched
    return {
        'match':      matched,
        'mismatch':   mismatched,
        'missing':    missing,
        'total':      total,
        'accuracy':   round(matched / comparable, 3) if comparable else None,
        'coverage':   round(comparable / total, 3)   if total else None,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model',     '-m', default='claude')
    parser.add_argument('--provinces', '-v', default=','.join(DEFAULT_PROVINCES))
    parser.add_argument('--limit',     '-l', type=int, default=None)
    parser.add_argument('--sleep',     type=float, default=0.3)
    parser.add_argument('--no-api',    action='store_true')
    parser.add_argument('--output',    '-o', default=None)
    args = parser.parse_args()

    provinces   = [p.strip() for p in args.provinces.split(',')]
    model_dir   = CAREER_DIR / args.model
    output_path = Path(args.output) if args.output else \
                  EVAL_DIR / f'name_eval_result_{args.model}.json'

    if not model_dir.exists():
        print(f'Error: {model_dir} not found'); return 1

    edh_by_hd = load_edh(provinces)
    corresp   = load_corresp()
    cg_index  = build_cg_index(model_dir)

    # HDリスト: correspがあればそれを優先、なければedh_by_hdのキー全体
    if corresp:
        hd_list = sorted(hd for hd in corresp if hd in edh_by_hd)
        print(f'Using corresp table. HD numbers in scope: {len(hd_list):,}')
    else:
        cache   = load_cache()
        hd_list = sorted(edh_by_hd.keys())
        print(f'No corresp table found, using API. HD numbers: {len(hd_list):,}')

    if args.limit:
        hd_list = hd_list[:args.limit]

    results        = []
    matched        = 0
    multi_matched  = 0

    for i, hd in enumerate(hd_list):
        # EDCS-IDリストを取得
        if corresp:
            edcs_ids = corresp.get(hd, [])
        else:
            session = requests.Session()
            session.headers['User-Agent'] = 'inscription-llm-evaluation/1.0'
            single = hd_to_edcs(hd, session, cache, args.sleep)
            edcs_ids = [single] if single else []

        if not edcs_ids:
            continue

        # 複数IDの場合はすべてのCGレコードのpersonsを統合
        # 重複人物は正規化名で除去
        found_ids  = []
        merged_persons = []
        seen_names = set()
        for eid in edcs_ids:
            rec = cg_index.get(eid)
            if not rec:
                continue
            found_ids.append(eid)
            for p in rec.get('persons', []):
                norm = re.sub(r'[^a-z]', '', (p.get('person_name', '') or '').lower())
                if norm and norm not in seen_names:
                    seen_names.add(norm)
                    merged_persons.append(p)
                elif not norm:
                    merged_persons.append(p)

        if not found_ids:
            continue

        if len(found_ids) > 1:
            multi_matched += 1

        matched += 1
        edh_persons = edh_by_hd[hd]
        pairs, unmatched_cg = align_persons(edh_persons, merged_persons)

        results.append({
            'hd_number':    hd,
            'edcs_id':      found_ids[0],
            'edcs_ids':     found_ids,
            'edh_count':    len(edh_persons),
            'cg_count':     len(merged_persons),
            'count_match':  len(edh_persons) == len(merged_persons),
            'pairs':        pairs,
            'unmatched_cg': unmatched_cg,
        })

        if (i + 1) % 100 == 0:
            print(f'  [{i+1}/{len(hd_list)}] matched: {matched}')

    if not corresp:
        save_cache(cache)
    if multi_matched:
        print(f'  (複数EDCS-IDから照合: {multi_matched}件)')

    # ── Aggregate all pairs ───────────────────────────────────────────────────
    all_pairs = [p for r in results for p in r['pairs']]
    print(f'\nTotal aligned person pairs: {len(all_pairs):,}')

    fields = ['m_praenomen', 'm_nomen', 'm_cognomen', 'm_gender']
    labels = ['praenomen',   'nomen',   'cognomen',   'gender']

    summary = {
        'provinces':             provinces,
        'edh_hd_in_scope':       len(hd_list),
        'matched_to_cg':         matched,
        'match_rate_pct':        round(matched / len(hd_list) * 100, 1) if hd_list else 0,
        'total_person_pairs':    len(all_pairs),
        'person_count_match_pct': round(
            sum(1 for r in results if r['count_match']) / len(results) * 100, 1
        ) if results else 0,
        'avg_name_overlap':      round(
            sum(p['name_overlap'] for p in all_pairs) / len(all_pairs), 3
        ) if all_pairs else 0,
        'fields': {},
    }

    print('\n=== Field Accuracy (EDH parsed vs CG) ===')
    print(f'{"Field":<15} {"Accuracy":>10} {"Coverage":>10} {"Match":>8} {"Mismatch":>10} {"Missing":>9}')
    print('-' * 65)

    for fkey, label in zip(fields, labels):
        r = rate(all_pairs, fkey)
        summary['fields'][label] = r
        acc = f"{r['accuracy']*100:.1f}%" if r['accuracy'] is not None else '  N/A'
        cov = f"{r['coverage']*100:.1f}%" if r['coverage'] is not None else '  N/A'
        print(f'{label:<15} {acc:>10} {cov:>10} {r["match"]:>8} {r["mismatch"]:>10} {r["missing"]:>9}')

    # Confidence breakdown for name fields
    print('\n=== Accuracy by EDH parse confidence ===')
    for conf in ('high', 'medium', 'low'):
        sub = [p for p in all_pairs if p['edh_conf'] == conf]
        if not sub:
            continue
        nom_r = rate(sub, 'm_nomen')
        cog_r = rate(sub, 'm_cognomen')
        nom_acc = f"{nom_r['accuracy']*100:.1f}%" if nom_r['accuracy'] is not None else 'N/A'
        cog_acc = f"{cog_r['accuracy']*100:.1f}%" if cog_r['accuracy'] is not None else 'N/A'
        print(f'  {conf:<8} (n={len(sub):,})  nomen={nom_acc}  cognomen={cog_acc}')

    # Save
    output = {'summary': summary, 'results': results}
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f'\nSaved to: {output_path}')

    # Plain-text summary
    txt_path = output_path.with_suffix('.txt')
    lines = ['=== Name Component Evaluation Summary ===', '']
    lines.append(f'Provinces : {", ".join(provinces)}')
    lines.append(f'EDH HD in scope : {len(hd_list):,}')
    lines.append(f'Matched to CG   : {matched:,} ({summary["match_rate_pct"]}%)')
    lines.append(f'Person pairs    : {len(all_pairs):,}')
    lines.append(f'Person count match: {summary["person_count_match_pct"]}%')
    lines.append(f'Avg name overlap  : {summary["avg_name_overlap"]}')
    lines.append('')
    lines.append(f'{"Field":<15} {"Accuracy":>10} {"Coverage":>10}')
    lines.append('-' * 37)
    for label in labels:
        r = summary['fields'][label]
        acc = f"{r['accuracy']*100:.1f}%" if r['accuracy'] is not None else 'N/A'
        cov = f"{r['coverage']*100:.1f}%" if r['coverage'] is not None else 'N/A'
        lines.append(f'{label:<15} {acc:>10} {cov:>10}')
    txt_path.write_text('\n'.join(lines), encoding='utf-8')
    print(f'Text summary: {txt_path}')

    # ── FP/FN detail log ──────────────────────────────────────────────────────
    log_path = output_path.with_name(output_path.stem + '_errors.txt')
    _write_error_log(results, log_path)
    print(f'Error log   : {log_path}')


def _write_error_log(results: list, log_path: Path):
    """Write FP/FN cases per inscription to a plain-text log."""

    checks = [
        ('praenomen', 'm_praenomen', 'edh_praenomen', 'cg_praenomen'),
        ('nomen',     'm_nomen',     'edh_nomen',     'cg_nomen'),
        ('cognomen',  'm_cognomen',  'edh_cognomen',  'cg_cognomen'),
        ('gender',    'm_gender',    'edh_gender',    'cg_gender'),
    ]

    lines = ['=== FP / FN Error Log ===', '']

    for r in results:
        if r['edh_count'] > 8:
            continue

        insc_errors = []
        for p in r['pairs']:
            if not p['aligned']:
                continue
            row_errors = []
            for label, fkey, edh_f, cg_f in checks:
                v = p[fkey]
                if v == 'mismatch':
                    row_errors.append(
                        f'    [FP] {label}: EDH={p[edh_f]!r}  CG={p[cg_f]!r}'
                    )
                elif v == 'missing' and p[edh_f] and not p[cg_f]:
                    row_errors.append(
                        f'    [FN] {label}: EDH={p[edh_f]!r}  CG=(空欄)'
                    )
            if row_errors:
                insc_errors.append(
                    f'  person: EDH={p["edh_name"]!r}  CG={p["cg_name"]!r}'
                    f'  overlap={p["name_overlap"]}'
                )
                insc_errors.extend(row_errors)

        if insc_errors:
            lines.append(
                f'[{r["hd_number"]}]  EDCS={r["edcs_id"]}'
                f'  EDH={r["edh_count"]}人  CG={r["cg_count"]}人'
            )
            lines.extend(insc_errors)
            lines.append('')

    log_path.write_text('\n'.join(lines), encoding='utf-8')


if __name__ == '__main__':
    main()
