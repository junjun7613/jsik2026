#!/usr/bin/env python3
"""
Convert EDH Linked Data TTL files to CSV for easier processing.

Province lookup chain:
  edh_people.ttl: person → lawd:hasAttestation → inschrift/HD000001
  edh_inscriptions.ttl: HD000001 → lawd:foundAt → geographie/XXXXX
  edh_geography.ttl: geographie/XXXXX → skos:broader → geographie/9XXXXX (province)

Outputs:
  edh_linked_data/edh_inscriptions.csv — one row per inscription
  edh_linked_data/edh_people.csv       — one row per person (province via inscription)
  edh_linked_data/edh_geography.csv    — one row per place

edh_inscriptions.csv columns:
  hd_number, geo_id, province_id, province_name, date_start, date_end,
  edition_text, diplomatic_text

edh_people.csv columns:
  hd_number, person_index, name, gender, social_status,
  date_start, date_end, province_id, province_name

edh_geography.csv columns:
  geo_id, label, province_id, province_name, country_code, lat, lon

Usage:
    python evaluation/convert_edh_ttl_to_csv.py
    python evaluation/convert_edh_ttl_to_csv.py --people-only
    python evaluation/convert_edh_ttl_to_csv.py --geo-only
    python evaluation/convert_edh_ttl_to_csv.py --inscriptions-only
"""

import re
import csv
import argparse
from pathlib import Path
from collections import Counter

LINKED_DATA_DIR  = Path(__file__).parent / 'edh_linked_data'
PEOPLE_TTL       = LINKED_DATA_DIR / 'edh_people.ttl'
GEO_TTL          = LINKED_DATA_DIR / 'edh_geography.ttl'
INSCRIPTIONS_TTL = LINKED_DATA_DIR / 'edh_inscriptions.ttl'
PEOPLE_CSV       = LINKED_DATA_DIR / 'edh_people.csv'
GEO_CSV          = LINKED_DATA_DIR / 'edh_geography.csv'
INSCRIPTIONS_CSV = LINKED_DATA_DIR / 'edh_inscriptions.csv'

GENDER_MAP = {
    'http://d-nb.info/standards/vocab/gnd/gender#male':   'male',
    'http://d-nb.info/standards/vocab/gnd/gender#female': 'female',
}

EDH_STATUS_MAP = {
    'senatorial_order':      'senatorial',
    'equestrian_order':      'equestrian',
    'decurial_order':        'decurial',
    'military_personnel':    'military',
    'imperial_household':    'imperial_household',
    'freedmen_freedwomen':   'freedman',
    'slaves':                'slave',
    'augustales':            'augustalis',
    'lower_local_officials': 'local_official',
    'rulers_foreign':        'foreign_ruler',
}


# ── Geography ─────────────────────────────────────────────────────────────────

def parse_geography() -> tuple[dict, dict]:
    """
    Returns:
      geo_info:     { geo_id: {label, province_id, province_name, country_code, lat, lon} }
      province_map: { province_geo_id: province_label }
    """
    print(f'Parsing {GEO_TTL.name} ...')
    geo_info = {}
    current_id = None
    current = {}

    with open(GEO_TTL, encoding='utf-8') as f:
        for line in f:
            stripped = line.strip()

            m = re.match(r'^<http://edh-www\.adw\.uni-heidelberg\.de/edh/geographie/(\d+)>', stripped)
            if m:
                if current_id and current:
                    geo_info[current_id] = current
                current_id = m.group(1)
                current = {'geo_id': current_id}
                continue

            if current_id is None:
                continue

            m = re.match(r'rdfs:label\s+"([^"]+)"', stripped)
            if m and 'label' not in current:
                current['label'] = m.group(1)
                continue

            m = re.match(r'gn:countryCode\s+"([^"]+)"', stripped)
            if m:
                current['country_code'] = m.group(1)
                continue

            m = re.match(r'skos:broader\s+<[^>]*/geographie/(\d+)>', stripped)
            if m:
                current['province_id'] = m.group(1)
                continue

            m = re.match(r'geo:lat\s+([\d.]+)', stripped)
            if m:
                current['lat'] = m.group(1)
                continue
            m = re.match(r'geo:long\s+([\d.]+)', stripped)
            if m:
                current['lon'] = m.group(1)
                continue

            if stripped in ('', '.') and current_id:
                geo_info[current_id] = current
                current_id = None
                current = {}

    if current_id and current:
        geo_info[current_id] = current

    # Province entries: geo_id = 9XXXXX (6 digits starting with 9)
    province_map = {}
    for gid, info in geo_info.items():
        if re.match(r'^9\d{5}$', gid):
            province_map[gid] = info.get('label', '')

    # Resolve province name for all places
    for info in geo_info.values():
        prov_id = info.get('province_id', '')
        info['province_name'] = province_map.get(prov_id, '')

    print(f'  Loaded {len(geo_info):,} places, {len(province_map)} provinces')
    return geo_info, province_map


def write_geo_csv(geo_info: dict):
    fieldnames = ['geo_id', 'label', 'province_id', 'province_name', 'country_code', 'lat', 'lon']
    rows = []
    for gid, info in sorted(geo_info.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0):
        rows.append({f: info.get(f, '') for f in fieldnames})
    with open(GEO_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f'  Saved {len(rows):,} rows → {GEO_CSV}')


# ── Inscriptions ──────────────────────────────────────────────────────────────

def parse_inscriptions(geo_info: dict) -> dict:
    """
    Parse edh_inscriptions.ttl.
    Returns { hd_number: {geo_id, province_id, province_name, date_start, date_end} }
    Province is resolved via lawd:foundAt → geo_info.
    """
    print(f'Parsing {INSCRIPTIONS_TTL.name} ...')
    inscriptions = {}
    current_hd = None
    current = {}

    with open(INSCRIPTIONS_TTL, encoding='utf-8') as f:
        for line in f:
            stripped = line.strip()

            m = re.match(
                r'^<http://edh-www\.adw\.uni-heidelberg\.de/edh/inschrift/(HD\d+)>$',
                stripped,
            )
            if m:
                if current_hd and current:
                    inscriptions[current_hd] = _finalize_inscription(current, geo_info)
                current_hd = m.group(1)
                current = {'hd_number': current_hd}
                continue

            if current_hd is None:
                continue

            # lawd:foundAt → geography ID
            m = re.match(r'lawd:foundAt\s+<[^>]*/geographie/(\d+)>', stripped)
            if m and 'geo_id' not in current:
                current['geo_id'] = m.group(1)
                continue

            m = re.match(r'nmo:hasStartDate\s+"([^"]+)"', stripped)
            if m:
                current['date_start'] = m.group(1)
                continue
            m = re.match(r'nmo:hasEndDate\s+"([^"]+)"', stripped)
            if m:
                current['date_end'] = m.group(1)
                continue

            m = re.match(r'epi:hasEditionText\s+"(.*)"@lat', stripped)
            if m:
                current['edition_text'] = m.group(1)
                continue
            m = re.match(r'epi:hasDiplomaticText\s+"(.*)"@lat', stripped)
            if m:
                current['diplomatic_text'] = m.group(1)
                continue

            if stripped in ('', '.') and current_hd:
                inscriptions[current_hd] = _finalize_inscription(current, geo_info)
                current_hd = None
                current = {}

    if current_hd and current:
        inscriptions[current_hd] = _finalize_inscription(current, geo_info)

    with_province = sum(1 for v in inscriptions.values() if v['province_name'])
    print(f'  Loaded {len(inscriptions):,} inscriptions, {with_province:,} with province')
    return inscriptions


def _finalize_inscription(current: dict, geo_info: dict) -> dict:
    geo_id = current.get('geo_id', '')
    place = geo_info.get(geo_id, {})
    return {
        'hd_number':      current.get('hd_number', ''),
        'geo_id':         geo_id,
        'province_id':    place.get('province_id', ''),
        'province_name':  place.get('province_name', ''),
        'date_start':     current.get('date_start', ''),
        'date_end':       current.get('date_end', ''),
        'edition_text':   current.get('edition_text', ''),
        'diplomatic_text': current.get('diplomatic_text', ''),
    }


def write_inscriptions_csv(inscriptions: dict):
    fieldnames = ['hd_number', 'geo_id', 'province_id', 'province_name', 'date_start', 'date_end',
                  'edition_text', 'diplomatic_text']
    rows = sorted(inscriptions.values(), key=lambda x: x['hd_number'])
    with open(INSCRIPTIONS_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f'  Saved {len(rows):,} rows → {INSCRIPTIONS_CSV}')


# ── People ────────────────────────────────────────────────────────────────────

def parse_people(inscriptions: dict) -> list[dict]:
    """
    Parse edh_people.ttl.
    Province is resolved via lawd:hasAttestation → HD number → inscriptions dict.
    """
    print(f'Parsing {PEOPLE_TTL.name} ...')
    persons = []
    current_uri = None
    current = {}

    with open(PEOPLE_TTL, encoding='utf-8') as f:
        for line in f:
            stripped = line.strip()

            m = re.match(
                r'^<http://edh-www\.adw\.uni-heidelberg\.de/edh/person/(HD\d+)/(\d+)>$',
                stripped,
            )
            if m:
                if current_uri and current:
                    persons.append(_finalize_person(current, inscriptions))
                current_uri = stripped
                current = {'hd_number': m.group(1), 'person_index': m.group(2)}
                continue

            if current_uri is None:
                continue

            m = re.match(r'lawd:PersonalName\s+"([^"]*)"', stripped)
            if m:
                current['name'] = m.group(1)
                continue

            m = re.match(r'gndo:gender\s+<([^>]+)>', stripped)
            if m:
                current['gender'] = GENDER_MAP.get(m.group(1), m.group(1).split('#')[-1])
                continue

            m = re.match(r'foaf:member\s+<[^>]*/social_status/([^>]+)>', stripped)
            if m:
                raw = m.group(1).rstrip('> .')
                current['social_status'] = EDH_STATUS_MAP.get(raw, raw)
                continue

            m = re.match(r'nmo:hasStartDate\s+"([^"]+)"', stripped)
            if m:
                current['date_start'] = m.group(1)
                continue
            m = re.match(r'nmo:hasEndDate\s+"([^"]+)"', stripped)
            if m:
                current['date_end'] = m.group(1)
                continue

            if stripped == '' and current_uri:
                if current:
                    persons.append(_finalize_person(current, inscriptions))
                current_uri = None
                current = {}

    if current_uri and current:
        persons.append(_finalize_person(current, inscriptions))

    with_province = sum(1 for p in persons if p['province_name'])
    print(f'  Loaded {len(persons):,} persons, {with_province:,} with province')
    return persons


def _finalize_person(current: dict, inscriptions: dict) -> dict:
    hd = current.get('hd_number', '')
    insc = inscriptions.get(hd, {})
    return {
        'hd_number':     hd,
        'person_index':  current.get('person_index', ''),
        'name':          current.get('name', ''),
        'gender':        current.get('gender', ''),
        'social_status': current.get('social_status', ''),
        'date_start':    current.get('date_start', ''),
        'date_end':      current.get('date_end', ''),
        'province_id':   insc.get('province_id', ''),
        'province_name': insc.get('province_name', ''),
    }


def write_people_csv(persons: list[dict]):
    fieldnames = [
        'hd_number', 'person_index', 'name', 'gender', 'social_status',
        'date_start', 'date_end', 'province_id', 'province_name',
    ]
    with open(PEOPLE_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(persons)
    print(f'  Saved {len(persons):,} rows → {PEOPLE_CSV}')


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Convert EDH TTL files to CSV')
    parser.add_argument('--people-only',       action='store_true')
    parser.add_argument('--geo-only',          action='store_true')
    parser.add_argument('--inscriptions-only', action='store_true')
    args = parser.parse_args()

    do_geo    = not args.people_only and not args.inscriptions_only
    do_insc   = not args.geo_only    and not args.people_only
    do_people = not args.geo_only    and not args.inscriptions_only

    geo_info     = {}
    inscriptions = {}

    if do_geo or do_insc or do_people:
        geo_info, _ = parse_geography()
        if do_geo:
            write_geo_csv(geo_info)

    if do_insc or do_people:
        inscriptions = parse_inscriptions(geo_info)
        if do_insc:
            write_inscriptions_csv(inscriptions)

    if do_people:
        persons = parse_people(inscriptions)
        write_people_csv(persons)

        prov_counts = Counter(p['province_name'] for p in persons)
        print('\nTop 20 provinces by person count:')
        for prov, cnt in prov_counts.most_common(20):
            print(f'  {prov or "(unknown)"}: {cnt:,}')


if __name__ == '__main__':
    main()
