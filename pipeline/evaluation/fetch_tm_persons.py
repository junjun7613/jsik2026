#!/usr/bin/env python3
"""
Fetch person data from Trismegistos for evaluation against career_graphs.

Pipeline:
  1. Read EDCS-IDs from career_graphs JSON files
  2. TexRelations API: EDCS-ID → TM Text ID + linked person IDs (TM Per IDs)
  3. PerResponder API: TM Per ID → person name, gender, attestations
  4. Save results to evaluation/tm_persons.json

Usage:
    python evaluation/fetch_tm_persons.py --model claude
    python evaluation/fetch_tm_persons.py --model claude --province Africa_proconsularis
    python evaluation/fetch_tm_persons.py --model claude --limit 100
    python evaluation/fetch_tm_persons.py --model claude --resume   # skip already fetched
"""

import json
import time
import argparse
from pathlib import Path

import requests

PIPELINE_DIR = Path(__file__).parent.parent
CAREER_GRAPHS_DIR = PIPELINE_DIR / 'provenance' / 'career_graphs'
OUTPUT_DIR = Path(__file__).parent

TEXRELATIONS_URL = 'https://www.trismegistos.org/dataservices/texrelations/{edcs_id}?source=edcs'
PERRESPONDER_URL = 'https://www.trismegistos.org/dataservices/rdf/per/index.php?id={per_id}&format=json'

# RDF predicate shortcuts
P_NAME    = 'http://lawd.info/ontology/PersonalName'
P_GENDER  = 'http://xmlns.com/foaf/0.1/gender'
P_REGION  = 'http://dbpedia.org/ontology/region'
P_DATE    = 'http://purl.org/dc/terms/date'


def iter_place_dirs(model_dir: Path):
    for entry in sorted(model_dir.iterdir()):
        if not entry.is_dir():
            continue
        if any(entry.glob('*.json')):
            yield entry
        else:
            for sub in sorted(entry.iterdir()):
                if sub.is_dir() and any(sub.glob('*.json')):
                    yield sub


def collect_edcs_ids(model_dir: Path, province: str = None, limit: int = None):
    """Collect (edcs_id, place_name, province_name) from career_graphs."""
    records = []
    for place_dir in iter_place_dirs(model_dir):
        province_name = place_dir.parent.name
        if province_name == model_dir.name:
            province_name = ''
        if province and province_name != province:
            continue
        for json_path in sorted(place_dir.glob('*.json')):
            try:
                data = json.loads(json_path.read_text(encoding='utf-8'))
            except Exception:
                continue
            for rec in data:
                edcs_id = rec.get('edcs_id', '')
                if edcs_id:
                    records.append({
                        'edcs_id': edcs_id,
                        'place': place_dir.name,
                        'province': province_name,
                    })
        if limit and len(records) >= limit:
            break
    return records[:limit] if limit else records


def parse_texrelations(response: list) -> dict:
    """Extract TM_ID and EDH from TexRelations response."""
    result = {}
    for item in response:
        for key, val in item.items():
            if val is not None:
                result[key] = val[0] if len(val) == 1 else val
    return result


def get_literal(data: dict, uri: str, pred: str):
    """Get first literal value for a predicate from PerResponder JSON-LD."""
    node = data.get(uri, {})
    values = node.get(pred, [])
    for v in values:
        if v.get('type') == 'literal':
            return v.get('value')
    return None


def fetch_texrelations(edcs_id: str, session: requests.Session) -> dict:
    url = TEXRELATIONS_URL.format(edcs_id=edcs_id.lstrip('EDCS-').lstrip('0') if False else edcs_id)
    # EDCS IDs in TexRelations are numeric only (strip 'EDCS-' prefix)
    numeric_id = edcs_id.replace('EDCS-', '').lstrip('0') or '0'
    url = TEXRELATIONS_URL.format(edcs_id=numeric_id)
    try:
        r = session.get(url, timeout=15)
        r.raise_for_status()
        return parse_texrelations(r.json())
    except Exception as e:
        return {'error': str(e)}


def fetch_person(per_id: str, session: requests.Session) -> dict:
    url = PERRESPONDER_URL.format(per_id=per_id)
    try:
        r = session.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        person_uri = f'https://www.trismegistos.org/person/{per_id}'
        return {
            'tm_per_id': per_id,
            'name': get_literal(data, person_uri, P_NAME),
            'gender': get_literal(data, person_uri, P_GENDER),
            'region': get_literal(data, person_uri, P_REGION),
            'date': get_literal(data, person_uri, P_DATE),
        }
    except Exception as e:
        return {'tm_per_id': per_id, 'error': str(e)}


def fetch_person_ids_for_text(tm_text_id: str, session: requests.Session) -> list:
    """
    Fetch person IDs linked to a TM text via the text page.
    Uses the TM text RDF endpoint to find associated persons.
    """
    url = f'https://www.trismegistos.org/dataservices/rdf/text/index.php?id={tm_text_id}&format=json'
    try:
        r = session.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        text_uri = f'https://www.trismegistos.org/text/{tm_text_id}'
        node = data.get(text_uri, {})
        person_pred = 'http://lawd.info/ontology/Person'
        persons = []
        for v in node.get(person_pred, []):
            if v.get('type') == 'uri':
                per_id = v['value'].split('/')[-1]
                persons.append(per_id)
        return persons
    except Exception:
        return []


def main():
    parser = argparse.ArgumentParser(description='Fetch Trismegistos person data for evaluation')
    parser.add_argument('--model', '-m', default='claude')
    parser.add_argument('--province', '-v', default=None,
                        help='Filter by province directory name')
    parser.add_argument('--limit', '-l', type=int, default=None,
                        help='Max number of EDCS records to process')
    parser.add_argument('--resume', action='store_true',
                        help='Skip EDCS IDs already in output file')
    parser.add_argument('--sleep', type=float, default=0.5,
                        help='Seconds between API calls (default: 0.5)')
    parser.add_argument('--output', '-o', default=None,
                        help='Output JSON path (default: evaluation/tm_persons_<model>.json)')
    args = parser.parse_args()

    model_dir = CAREER_GRAPHS_DIR / args.model
    if not model_dir.exists():
        print(f'Error: {model_dir} not found')
        return 1

    output_path = Path(args.output) if args.output else \
        OUTPUT_DIR / f'tm_persons_{args.model}.json'

    # Resume: load existing results
    existing = {}
    if args.resume and output_path.exists():
        try:
            existing = {r['edcs_id']: r
                        for r in json.loads(output_path.read_text(encoding='utf-8'))}
            print(f'Resuming: {len(existing)} records already fetched')
        except Exception:
            pass

    records = collect_edcs_ids(model_dir, province=args.province, limit=args.limit)
    print(f'EDCS records to process: {len(records)}')

    session = requests.Session()
    session.headers['User-Agent'] = 'inscription-llm-evaluation/1.0 (research)'

    results = list(existing.values())
    done_ids = set(existing.keys())

    for i, rec in enumerate(records):
        edcs_id = rec['edcs_id']
        if edcs_id in done_ids:
            continue

        print(f'[{i+1}/{len(records)}] {edcs_id}', end=' ... ', flush=True)

        # Step 1: EDCS-ID → TM Text ID
        tx = fetch_texrelations(edcs_id, session)
        time.sleep(args.sleep)

        tm_text_id = tx.get('TM_ID')
        edh_id = tx.get('EDH')
        if not tm_text_id:
            print('no TM ID')
            results.append({**rec, 'tm_text_id': None, 'edh_id': edh_id, 'persons': []})
            done_ids.add(edcs_id)
            continue

        # Step 2: TM Text ID → linked person IDs
        per_ids = fetch_person_ids_for_text(tm_text_id, session)
        time.sleep(args.sleep)

        # Step 3: fetch each person
        persons = []
        for per_id in per_ids:
            p = fetch_person(per_id, session)
            persons.append(p)
            time.sleep(args.sleep)

        print(f'TM={tm_text_id}, EDH={edh_id}, persons={len(persons)}')
        results.append({
            **rec,
            'tm_text_id': tm_text_id,
            'edh_id': edh_id,
            'persons': persons,
        })
        done_ids.add(edcs_id)

        # Save every 50 records
        if len(results) % 50 == 0:
            output_path.write_text(
                json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')

    output_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')

    with_persons = sum(1 for r in results if r.get('persons'))
    print(f'\nDone. Total: {len(results)}, with TM persons: {with_persons}')
    print(f'Saved to: {output_path}')


if __name__ == '__main__':
    main()
