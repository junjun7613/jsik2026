#!/usr/bin/env python3
"""
Evaluate career_graphs person data against EDH prosopography.

Approach (reverse lookup):
  1. Read edh_people.csv + edh_inscriptions.csv (pre-built from TTL)
  2. Filter to target provinces (Africa Proconsularis, Numidia by default)
  3. For each HD number in scope, call TexRelations HD→EDCS to get EDCS-ID
  4. Check if that EDCS-ID exists in career_graphs
  5. Compare persons: name token overlap, gender, social_status

This avoids coverage bias: we start from what EDH has, not from career_graphs.

Usage:
    python evaluation/evaluate_against_edh.py --model claude
    python evaluation/evaluate_against_edh.py --model claude --provinces "Africa Proconsularis,Numidia"
    python evaluation/evaluate_against_edh.py --model claude --limit 200
    python evaluation/evaluate_against_edh.py --model claude --no-api   # cached only
"""

import json
import time
import re
import csv
import argparse
from pathlib import Path
from collections import defaultdict

import requests

EVAL_DIR      = Path(__file__).parent
PIPELINE_DIR  = EVAL_DIR.parent
CAREER_DIR    = PIPELINE_DIR / 'provenance' / 'career_graphs'
LINKED_DIR    = EVAL_DIR / 'edh_linked_data'
PEOPLE_CSV    = LINKED_DIR / 'edh_people.csv'
INSCR_CSV     = LINKED_DIR / 'edh_inscriptions.csv'
CACHE_PATH    = EVAL_DIR / 'hd_to_edcs_cache.json'

TEXRELATIONS  = 'https://www.trismegistos.org/dataservices/texrelations/{id}?source=edh'

DEFAULT_PROVINCES = ['Africa Proconsularis', 'Numidia']


# ── Step 1: Load EDH CSVs ─────────────────────────────────────────────────────

def load_edh_persons_by_hd(provinces: list[str]) -> dict:
    """
    Returns { hd_number: [ {name, gender, social_status, date_start, date_end}, ... ] }
    filtered to the given provinces.
    """
    # Build HD→province map from inscriptions CSV (authoritative province source)
    hd_province = {}
    with open(INSCR_CSV, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            hd_province[row['hd_number']] = row['province_name']

    target = set(provinces)
    hd_persons = defaultdict(list)

    with open(PEOPLE_CSV, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            hd = row['hd_number']
            prov = hd_province.get(hd, row.get('province_name', ''))
            if prov not in target:
                continue
            hd_persons[hd].append({
                'name':          row['name'],
                'gender':        row['gender'],
                'social_status': row['social_status'],
                'date_start':    row['date_start'],
                'date_end':      row['date_end'],
            })

    total = sum(len(v) for v in hd_persons.values())
    print(f'EDH persons in scope: {total:,} across {len(hd_persons):,} inscriptions')
    return dict(hd_persons)


# ── Step 2: HD → EDCS via TexRelations ───────────────────────────────────────

def load_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding='utf-8'))
    return {}


def save_cache(cache: dict):
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding='utf-8')


def hd_to_edcs(hd_number: str, session: requests.Session, cache: dict, sleep: float) -> str | None:
    """
    Query TexRelations with source=edh to get EDCS-ID for a given HD number.
    Returns 'EDCS-XXXXXXXX' or None.
    TexRelations expects the full HD-prefixed format: HD000370
    """
    if hd_number in cache:
        return cache[hd_number]

    url = TEXRELATIONS.format(id=hd_number)
    try:
        r = session.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and 'EDCS' in item and item['EDCS']:
                    edcs_raw = item['EDCS'][0] if isinstance(item['EDCS'], list) else item['EDCS']
                    # Normalize: TexRelations returns 8-digit numeric string → EDCS-XXXXXXXX
                    edcs_id = f"EDCS-{str(edcs_raw).zfill(8)}"
                    cache[hd_number] = edcs_id
                    return edcs_id
        cache[hd_number] = None
        return None
    except Exception:
        return None
    finally:
        time.sleep(sleep)


# ── Step 3: Build career_graphs index ────────────────────────────────────────

def build_cg_index(model_dir: Path) -> dict:
    """
    Returns { edcs_id: record } from all career_graphs JSON files.
    """
    index = {}
    for entry in sorted(model_dir.iterdir()):
        if not entry.is_dir():
            continue
        subdirs = [entry] if any(entry.glob('*.json')) else [
            sub for sub in sorted(entry.iterdir()) if sub.is_dir()
        ]
        for place_dir in subdirs:
            for json_path in sorted(place_dir.glob('*.json')):
                try:
                    data = json.loads(json_path.read_text(encoding='utf-8'))
                    for rec in data:
                        eid = rec.get('edcs_id', '')
                        if eid:
                            index[eid] = rec
                except Exception:
                    continue

    print(f'Career graph index: {len(index):,} records')
    return index


# ── Step 4: Compare persons ───────────────────────────────────────────────────

def normalize_name(name: str) -> set:
    if not name:
        return set()
    return set(re.sub(r'[^a-z]', ' ', name.lower()).split())


def name_overlap(edh_name: str, cg_name: str) -> float:
    a = normalize_name(edh_name)
    b = normalize_name(cg_name)
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a), len(b))


def compare_inscription(edh_persons: list, cg_record: dict) -> dict:
    cg_persons = cg_record.get('persons', [])
    edh_count  = len(edh_persons)
    cg_count   = len(cg_persons)

    matched_pairs = []
    for edh_p in edh_persons:
        best_score = 0.0
        best_cg    = None
        for cg_p in cg_persons:
            score = name_overlap(edh_p.get('name', ''), cg_p.get('person_name', ''))
            if score > best_score:
                best_score = score
                best_cg    = cg_p
        matched_pairs.append({
            'edh_name':   edh_p.get('name', ''),
            'edh_gender': edh_p.get('gender', ''),
            'edh_status': edh_p.get('social_status', ''),
            'cg_name':    best_cg.get('person_name', '') if best_cg else '',
            'cg_gender':  best_cg.get('gender', '')      if best_cg else '',
            'cg_status':  best_cg.get('social_status', '') if best_cg else '',
            'name_score': round(best_score, 3),
        })

    name_scores = [p['name_score'] for p in matched_pairs]
    avg_name    = sum(name_scores) / len(name_scores) if name_scores else 0.0

    return {
        'edh_count':      edh_count,
        'cg_count':       cg_count,
        'count_match':    edh_count == cg_count,
        'avg_name_score': round(avg_name, 3),
        'pairs':          matched_pairs,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Evaluate career_graphs against EDH (reverse lookup)')
    parser.add_argument('--model',     '-m', default='claude')
    parser.add_argument('--provinces', '-v',
                        default=','.join(DEFAULT_PROVINCES),
                        help='Comma-separated province names (default: Africa Proconsularis,Numidia)')
    parser.add_argument('--limit',     '-l', type=int, default=None,
                        help='Max HD numbers to process')
    parser.add_argument('--sleep',     type=float, default=0.3)
    parser.add_argument('--no-api',    action='store_true',
                        help='Use cached HD→EDCS map only, skip API calls')
    parser.add_argument('--output',    '-o', default=None)
    args = parser.parse_args()

    provinces = [p.strip() for p in args.provinces.split(',')]

    model_dir = CAREER_DIR / args.model
    if not model_dir.exists():
        print(f'Error: {model_dir} not found')
        return 1

    output_path = Path(args.output) if args.output else \
        EVAL_DIR / f'evaluation_result_{args.model}.json'

    # Step 1: EDH persons in scope (province-filtered)
    edh_by_hd = load_edh_persons_by_hd(provinces)

    # Step 2: HD → EDCS cache
    cache = load_cache()
    print(f'HD→EDCS cache: {len(cache)} entries')

    # Step 3: career_graphs index
    cg_index = build_cg_index(model_dir)

    # Limit
    hd_list = sorted(edh_by_hd.keys())
    if args.limit:
        hd_list = hd_list[:args.limit]
    print(f'HD numbers to process: {len(hd_list):,}')

    session = requests.Session()
    session.headers['User-Agent'] = 'inscription-llm-evaluation/1.0'

    results      = []
    matched_cg   = 0
    api_calls    = 0

    for i, hd in enumerate(hd_list):
        # HD → EDCS
        if args.no_api:
            edcs_id = cache.get(hd)
        else:
            edcs_id = hd_to_edcs(hd, session, cache, args.sleep)
            api_calls += 1
            if api_calls % 100 == 0:
                save_cache(cache)

        if not edcs_id:
            continue

        # Check career_graphs
        cg_rec = cg_index.get(edcs_id)
        if not cg_rec:
            continue

        matched_cg += 1
        edh_persons = edh_by_hd[hd]
        cmp = compare_inscription(edh_persons, cg_rec)
        cmp['hd_number'] = hd
        cmp['edcs_id']   = edcs_id
        results.append(cmp)

        if (i + 1) % 50 == 0:
            print(f'  [{i+1}/{len(hd_list)}] CG matches so far: {matched_cg}')

    save_cache(cache)

    # ── Summary ───────────────────────────────────────────────────────────────
    if results:
        avg_name  = sum(r['avg_name_score'] for r in results) / len(results)
        count_ok  = sum(1 for r in results if r['count_match'])
        high_name = sum(1 for r in results if r['avg_name_score'] >= 0.5)

        summary = {
            'provinces':              provinces,
            'edh_hd_in_scope':        len(hd_list),
            'matched_to_cg':          matched_cg,
            'match_rate_pct':         round(matched_cg / len(hd_list) * 100, 1),
            'inscriptions_compared':  len(results),
            'avg_name_score':         round(avg_name, 3),
            'person_count_match_pct': round(count_ok / len(results) * 100, 1),
            'name_score_ge_0.5_pct':  round(high_name / len(results) * 100, 1),
        }
    else:
        summary = {'note': 'No matching inscriptions found'}

    output = {'summary': summary, 'results': results}
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')

    print('\n=== Evaluation Summary ===')
    for k, v in summary.items():
        print(f'  {k}: {v}')
    print(f'\nSaved to: {output_path}')


if __name__ == '__main__':
    main()
