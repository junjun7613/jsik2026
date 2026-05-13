#!/usr/bin/env python3
"""
Sample 100 inscriptions from Africa Proconsularis + Numidia career_graphs
for manual EDH evaluation.

Stratification axes:
  A. inscription_text_length:  short (<100 chars), medium (100-300), long (>300)
  B. person_count:             1 person, 2+ persons
  C. career_richness:          no career, has career (career_path non-empty)
  D. content_richness:         sparse (few fields filled), rich (many fields filled)

Target distribution (100 total):
  - 40 short / 40 medium / 20 long  (text length)
  - 70 single-person / 30 multi-person
  - 50 with career / 50 without career
  Balanced across career_richness within each length stratum.

Output:
  evaluation/manual_eval_sample.csv  — fields for manual lookup + annotation
"""

import json
import csv
import random
from pathlib import Path

PIPELINE_DIR = Path(__file__).parent.parent.parent
CAREER_DIR   = PIPELINE_DIR / 'provenance' / 'career_graphs'
OUTPUT_PATH  = Path(__file__).parent / 'manual_eval_sample.csv'

PROVINCES = ['Africa_proconsularis', 'Numidia']
TARGET_N  = 100
RANDOM_SEED = 42


def iter_records(model_dir: Path, provinces: list[str]):
    for prov in provinces:
        prov_dir = model_dir / prov
        if not prov_dir.exists():
            continue
        for place_dir in sorted(prov_dir.iterdir()):
            if not place_dir.is_dir():
                continue
            for json_path in sorted(place_dir.glob('*.json')):
                try:
                    data = json.loads(json_path.read_text(encoding='utf-8'))
                    for rec in data:
                        yield rec, prov
                except Exception:
                    continue


def content_score(rec: dict) -> int:
    """Simple score 0-10 reflecting how much structured content exists."""
    score = 0
    persons = rec.get('persons', [])
    for p in persons:
        if p.get('social_status'):    score += 1
        if p.get('gender'):           score += 1
        if p.get('nomen'):            score += 1
        if p.get('cognomen'):         score += 1
        if p.get('career_path'):      score += 2
        if p.get('age_at_death'):     score += 1
    if rec.get('communities'):        score += 1
    if rec.get('person_relationships'): score += 1
    if rec.get('benefactions'):       score += 1
    return score


def classify_record(rec: dict, prov: str) -> dict:
    orig     = rec.get('original_data', {})
    insc_text = orig.get('inscription_conservative_cleaning', '') or \
                orig.get('inscription', '') or ''
    text_len = len(insc_text)

    persons  = rec.get('persons', [])
    n_persons = len(persons)
    has_career = any(p.get('career_path') for p in persons)
    richness  = content_score(rec)

    if text_len < 100:
        length_bin = 'short'
    elif text_len < 300:
        length_bin = 'medium'
    else:
        length_bin = 'long'

    return {
        'edcs_id':      rec.get('edcs_id', ''),
        'province':     prov,
        'place':        orig.get('place', ''),
        'publication':  orig.get('publication', ''),
        'inscription_text': insc_text,
        'text_length':  text_len,
        'length_bin':   length_bin,
        'n_persons':    n_persons,
        'has_career':   has_career,
        'content_score': richness,
        # EDH lookup fields (to be filled manually)
        'edh_hd_number': '',
        'edh_persons_count': '',
        # Per-person annotation columns (up to 3 persons)
        'p1_name':      persons[0].get('person_name', '') if n_persons > 0 else '',
        'p1_praenomen': persons[0].get('praenomen', '')   if n_persons > 0 else '',
        'p1_nomen':     persons[0].get('nomen', '')       if n_persons > 0 else '',
        'p1_cognomen':  persons[0].get('cognomen', '')    if n_persons > 0 else '',
        'p1_gender':    persons[0].get('gender', '')      if n_persons > 0 else '',
        'p1_status':    persons[0].get('social_status', '') if n_persons > 0 else '',
        # EDH ground-truth columns (blank — to be filled manually)
        'edh_p1_praenomen': '',
        'edh_p1_nomen':     '',
        'edh_p1_cognomen':  '',
        'edh_p1_gender':    '',
        'edh_p1_status':    '',
        'edh_p2_name':      '',
        'edh_p2_praenomen': '',
        'edh_p2_nomen':     '',
        'edh_p2_cognomen':  '',
        'edh_p2_gender':    '',
        'edh_p2_status':    '',
        'notes': '',
    }


def stratified_sample(records: list[dict], n: int, seed: int) -> list[dict]:
    """
    Fixed-quota sampling to ensure evaluation coverage of interesting cases.

    Target quotas (sum = 100):
      text length:   short=40, medium=35, long=25
      has_career:    True=50,  False=50
      multi_person:  True=35,  False=65
    We sample by crossing (length_bin × has_career) in fixed proportions,
    then within each cell prefer higher content_score records.
    """
    rng = random.Random(seed)

    # Fixed target: (length_bin, has_career) → quota
    fixed_quotas = {
        ('short',  True):  20,
        ('short',  False): 20,
        ('medium', True):  18,
        ('medium', False): 17,
        ('long',   True):  12,
        ('long',   False): 13,
    }

    # Build pools per cell
    pools: dict[tuple, list] = {k: [] for k in fixed_quotas}
    for r in records:
        key = (r['length_bin'], r['has_career'])
        if key in pools:
            pools[key].append(r)

    sampled = []
    for key, quota in fixed_quotas.items():
        pool = pools[key]
        if not pool:
            continue
        # Prefer records with higher content_score
        pool_sorted = sorted(pool, key=lambda r: -r['content_score'])
        # Sample from top 60% (richer half) to keep variety
        top = max(quota, int(len(pool_sorted) * 0.6))
        candidates = pool_sorted[:top]
        chosen = rng.sample(candidates, min(quota, len(candidates)))
        sampled.extend(chosen)

    rng.shuffle(sampled)
    return sampled[:n]


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', '-m', default='claude')
    parser.add_argument('--n',     '-n', type=int, default=TARGET_N)
    parser.add_argument('--seed',  type=int, default=RANDOM_SEED)
    parser.add_argument('--output', '-o', default=None)
    args = parser.parse_args()

    model_dir   = CAREER_DIR / args.model
    output_path = Path(args.output) if args.output else OUTPUT_PATH

    print(f'Loading records from {model_dir} ...')
    all_classified = []
    for rec, prov in iter_records(model_dir, PROVINCES):
        if rec.get('edcs_id'):
            all_classified.append(classify_record(rec, prov))

    print(f'Total records: {len(all_classified):,}')

    # Print stratum overview
    from collections import Counter
    bin_counts = Counter(r['length_bin'] for r in all_classified)
    career_counts = Counter(r['has_career'] for r in all_classified)
    multi_counts  = Counter(r['n_persons'] >= 2 for r in all_classified)
    print(f'Text length bins: {dict(bin_counts)}')
    print(f'Has career: {dict(career_counts)}')
    print(f'Multi-person: {dict(multi_counts)}')

    sampled = stratified_sample(all_classified, args.n, args.seed)

    # Sort by province then place for easier manual lookup
    sampled.sort(key=lambda r: (r['province'], r['place']))

    fieldnames = [
        'edcs_id', 'province', 'place', 'publication',
        'length_bin', 'text_length', 'n_persons', 'has_career', 'content_score',
        'inscription_text',
        'p1_name', 'p1_praenomen', 'p1_nomen', 'p1_cognomen', 'p1_gender', 'p1_status',
        'edh_hd_number', 'edh_persons_count',
        'edh_p1_praenomen', 'edh_p1_nomen', 'edh_p1_cognomen', 'edh_p1_gender', 'edh_p1_status',
        'edh_p2_name', 'edh_p2_praenomen', 'edh_p2_nomen', 'edh_p2_cognomen',
        'edh_p2_gender', 'edh_p2_status',
        'notes',
    ]

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(sampled)

    print(f'\nSampled {len(sampled)} records → {output_path}')

    # Stratum breakdown of sample
    s_bins    = Counter(r['length_bin'] for r in sampled)
    s_career  = Counter(r['has_career'] for r in sampled)
    s_multi   = Counter(r['n_persons'] >= 2 for r in sampled)
    print(f'Sample length bins:  {dict(s_bins)}')
    print(f'Sample has_career:   {dict(s_career)}')
    print(f'Sample multi-person: {dict(s_multi)}')


if __name__ == '__main__':
    main()
