#!/usr/bin/env python3
"""
Parse Roman personal names (PersonalName string) into praenomen/nomen/cognomen.

Roman name conventions:
  Tria nomina: Praenomen Nomen Cognomen  (e.g. "C. Iulius Caesar")
  Duo nomina:  Nomen Cognomen            (e.g. "Iulius Caesar")
  Single name: Cognomen only             (slaves, foreigners)
  Women:       often Nomen + Cognomen (no praenomen)

Praenomen list (standard abbreviations and full forms):
  A. = Aulus, C. = Gaius, Cn. = Gnaeus, D. = Decimus, K. = Kaeso,
  L. = Lucius, M. = Marcus, M'. = Manius, N. = Numerius, P. = Publius,
  Q. = Quintus, Ser. = Servius, Sex. = Sextus, Sp. = Spurius, T. = Titus,
  Ti. = Tiberius, V. = Vibius

Usage:
  from parse_roman_names import parse_name
  result = parse_name("C. Iulius Caesar")
  # -> {'praenomen': 'C.', 'nomen': 'Iulius', 'cognomen': 'Caesar', 'extra': ''}
"""

import re

# Standard praenomina (abbreviations first for matching priority)
PRAENOMINA_ABBR = {
    "A.", "C.", "Cn.", "D.", "K.", "L.", "M.", "M'.", "N.", "P.",
    "Q.", "Ser.", "Sex.", "Sp.", "T.", "Ti.", "V.",
}

PRAENOMINA_FULL = {
    "Aulus", "Gaius", "Gnaeus", "Decimus", "Kaeso", "Lucius", "Marcus",
    "Manius", "Numerius", "Publius", "Quintus", "Servius", "Sextus",
    "Spurius", "Titus", "Tiberius", "Vibius",
}

PRAENOMINA_ALL = PRAENOMINA_ABBR | PRAENOMINA_FULL

# Particles/connectors to skip
SKIP_TOKENS = {"et", "vel", "sive", "und", "f.", "fil.", "lib.", "l.",
               "filia", "filius", "libertus", "liberta"}

# Lacuna markers (reconstruction brackets)
LACUNA_RE = re.compile(r'\[[\d\s\-]+\]|\[[-]+\]|---+')


def _clean(name: str) -> str:
    """Remove lacuna markers and normalize whitespace."""
    name = LACUNA_RE.sub(' ', name)
    return re.sub(r'\s+', ' ', name).strip()


def parse_name(raw_name: str) -> dict:
    """
    Parse a Latin personal name string into components.

    Returns dict with keys:
      praenomen, nomen, cognomen, extra, confidence
      confidence: 'high' | 'medium' | 'low'
    """
    if not raw_name or not raw_name.strip():
        return _empty()

    name = _clean(raw_name)
    tokens = name.split()
    if not tokens:
        return _empty()

    praenomen = ''
    nomen     = ''
    cognomen  = ''
    extra     = ''

    idx = 0

    # Check for praenomen at position 0
    if tokens[0] in PRAENOMINA_ALL:
        praenomen = tokens[0]
        idx = 1

    remaining = [t for t in tokens[idx:] if t.lower() not in SKIP_TOKENS]

    if not remaining:
        # Only praenomen or nothing usable
        confidence = 'low'
        return {
            'praenomen': praenomen,
            'nomen': '', 'cognomen': '', 'extra': '',
            'confidence': confidence,
        }

    if len(remaining) == 1:
        # Single token: could be nomen or cognomen
        # Heuristic: ends in -us/-ius/-anus → nomen; otherwise cognomen
        tok = remaining[0]
        if re.search(r'(ius|ianus|eius)$', tok, re.I):
            nomen     = tok
            confidence = 'medium'
        else:
            cognomen   = tok
            confidence = 'medium' if not praenomen else 'high'
        return {
            'praenomen': praenomen, 'nomen': nomen, 'cognomen': cognomen,
            'extra': '', 'confidence': confidence,
        }

    if len(remaining) == 2:
        nomen    = remaining[0]
        cognomen = remaining[1]
        confidence = 'high' if praenomen else 'medium'
        return {
            'praenomen': praenomen, 'nomen': nomen, 'cognomen': cognomen,
            'extra': '', 'confidence': confidence,
        }

    # 3+ tokens: nomen + cognomen + extra (agnomen, signum, etc.)
    nomen    = remaining[0]
    cognomen = remaining[1]
    extra    = ' '.join(remaining[2:])
    confidence = 'medium'  # extra parts reduce confidence

    return {
        'praenomen': praenomen, 'nomen': nomen, 'cognomen': cognomen,
        'extra': extra, 'confidence': confidence,
    }


def _empty() -> dict:
    return {'praenomen': '', 'nomen': '', 'cognomen': '', 'extra': '', 'confidence': 'low'}


# ── Batch enrichment of edh_people.csv ────────────────────────────────────────

def enrich_people_csv(input_csv: str, output_csv: str):
    import csv
    from pathlib import Path

    rows = []
    with open(input_csv, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        original_fields = reader.fieldnames
        for row in reader:
            parsed = parse_name(row['name'])
            row['parsed_praenomen'] = parsed['praenomen']
            row['parsed_nomen']     = parsed['nomen']
            row['parsed_cognomen']  = parsed['cognomen']
            row['parsed_extra']     = parsed['extra']
            row['parse_confidence'] = parsed['confidence']
            rows.append(row)

    new_fields = original_fields + [
        'parsed_praenomen', 'parsed_nomen', 'parsed_cognomen',
        'parsed_extra', 'parse_confidence',
    ]
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=new_fields)
        writer.writeheader()
        writer.writerows(rows)

    conf_counts = {}
    for r in rows:
        c = r['parse_confidence']
        conf_counts[c] = conf_counts.get(c, 0) + 1
    total = len(rows)
    print(f'Parsed {total:,} names:')
    for c in ('high', 'medium', 'low'):
        n = conf_counts.get(c, 0)
        print(f'  {c}: {n:,} ({n/total*100:.1f}%)')
    print(f'Saved to: {output_csv}')


if __name__ == '__main__':
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description='Parse Roman names in edh_people.csv')
    parser.add_argument('--input',  default=None)
    parser.add_argument('--output', default=None)
    args = parser.parse_args()

    default_dir = Path(__file__).parent / 'edh_linked_data'
    input_csv  = args.input  or str(default_dir / 'edh_people.csv')
    output_csv = args.output or str(default_dir / 'edh_people_parsed.csv')

    enrich_people_csv(input_csv, output_csv)
