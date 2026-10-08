#!/usr/bin/env python3
"""
PROTOTYPE — not part of the pipeline.

Trial generator for the "layered EntityReference" proposal (案E): record each
interpretation act's contribution to a PersonReference in its own named graph,
dated by that act, instead of folding every act's output into one graph named
after the extract run.

Purpose is measurement, not production: it reports how many graphs and triples
the scheme costs relative to the current output, so the cost of a full
regeneration can be judged before committing to it.

Usage:
    python provenance/prototype_layered_entityref.py EDCS-25401734 [...]
    python provenance/prototype_layered_entityref.py --sample 50
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from create_rdf_himiko import (  # noqa: E402
    ACTIVITY_NS, GRAPH_NS, _activity_uri, _eref_person, _lit, _safe_id,
)

SRC = Path(__file__).parent / 'validated_career_graphs' / 'claude'

# JSON person field -> RDF predicate. Only fields an act actually writes onto a
# PersonReference; career/benefaction fields live on their own statements.
PERSON_FIELD_PREDICATE = {
    'person_name':                        'epig:personName',
    'praenomen':                          'epig:praenomen',
    'nomen':                              'epig:nomen',
    'cognomen':                           'epig:cognomen',
    'person_name_normalized':             'epig:normalizedName',
    'gender':                             'epig:gender',
    'gender_evidence':                    'epig:genderEvidence',
    'ethnicity':                          'epig:ethnicity',
    'ethnicity_evidence':                 'epig:ethnicityEvidence',
    'social_status':                      'epig:socialStatus',
    'social_status_evidence':             'epig:socialStatusEvidence',
    'age_at_death':                       'epig:ageAtDeath',
    'age_at_death_evidence':              'epig:ageAtDeathEvidence',
    'divinity':                           'epig:isDivinity',
    'divinity_type':                      'epig:divinityType',
    'divinity_classification_reasoning':  'epig:divinityClassificationReasoning',
}

BOOL_FIELDS = {'divinity'}
INT_FIELDS = {'age_at_death'}

# life_events is a nested list; one act writes it but it expands to several
# predicates, so it is expanded separately rather than via the table above.
LIFE_EVENT_PREDICATES = {
    ('birth', 'place'):            'epig:birthPlace',
    ('birth', 'place_normalized'): 'epig:birthPlaceNormalized',
    ('birth', 'place_evidence'):   'epig:birthPlaceEvidence',
    ('death', 'place'):            'epig:deathPlace',
    ('death', 'place_normalized'): 'epig:deathPlaceNormalized',
    ('death', 'place_evidence'):   'epig:deathPlaceEvidence',
    ('death', 'place_source'):     'epig:deathPlaceSource',
}


def _empty(v):
    return v is None or v == '' or v == [] or v == {}


def _field_owner(activities: list) -> dict:
    """Map 'persons[].<field>' -> the activity dict that generated it."""
    owner = {}
    for act in activities:
        for label in act.get('generated_fields', []):
            if label.startswith('persons[].'):
                owner[label[len('persons[].'):]] = act
    return owner


def _graph_name(edcs_id: str, act: dict) -> str:
    """Graph named for the act that wrote it, dated by when that act ran."""
    kind = act.get('type', 'unknown')
    ts = (act.get('timestamp') or '').replace('-', '').replace(':', '')
    if kind == 'extract':
        # Keep the familiar claude/<date> name for the base layer so existing
        # references to it stay meaningful.
        return f'{GRAPH_NS}{_safe_id(edcs_id)}/claude/{(act.get("timestamp") or "")[:10]}'
    return f'{GRAPH_NS}{_safe_id(edcs_id)}/{kind}/{ts}'


def _person_value_lines(person: dict, field: str) -> list:
    """Emit 'predicate value ;' lines for one JSON field."""
    value = person.get(field)
    if _empty(value):
        return []
    if field == 'life_events':
        out = []
        for ev in value:
            etype = ev.get('event_type', '')
            for key, pred in LIFE_EVENT_PREDICATES.items():
                if key[0] != etype:
                    continue
                v = ev.get(key[1])
                if not _empty(v):
                    out.append(f'    {pred} {_lit(v)} ;')
        return out
    pred = PERSON_FIELD_PREDICATE.get(field)
    if not pred:
        return []
    if field in BOOL_FIELDS:
        return [f'    {pred} "{str(value).lower()}"^^xsd:boolean ;']
    if field in INT_FIELDS:
        try:
            return [f'    {pred} "{int(value)}"^^xsd:integer ;']
        except (ValueError, TypeError):
            return []
    return [f'    {pred} {_lit(value)} ;']


def build_layers(record: dict) -> dict:
    """
    Return {graph_uri: [turtle lines]} for one record's PersonReferences,
    one graph per interpretation act that contributed any person attribute.
    """
    edcs_id = record.get('edcs_id', 'Unknown')
    activities = record.get('_provenance', {}).get('activities', [])
    owner = _field_owner(activities)

    extract_act = next((a for a in activities if a.get('type') == 'extract'), None)
    layers = defaultdict(list)

    for person in record.get('persons', []):
        if person.get('person_name', '') in ('Parse Error', 'Error', 'No Text'):
            continue
        p_uri = _eref_person(edcs_id, person.get('person_id', 0))

        # Group this person's populated fields by the act that wrote them.
        by_act = defaultdict(list)
        for field in list(PERSON_FIELD_PREDICATE) + ['life_events']:
            if _empty(person.get(field)):
                continue
            act = owner.get(field) or extract_act
            if act is None:
                continue
            by_act[_graph_name(edcs_id, act)].append((field, act))

        for graph_uri, entries in by_act.items():
            act = entries[0][1]
            body = [f'  {p_uri}']
            # rdf:type belongs to the layer that first created the reference.
            if act.get('type') == 'extract':
                body.append('    a epig:PersonReference ;')
                surface = (person.get('person_name_readable')
                           or person.get('person_name', ''))
                if surface:
                    body.append(f'    hmki:surfaceForm {_lit(surface)} ;')
            for field, _ in entries:
                body += _person_value_lines(person, field)
            act_uri = _activity_uri(act.get('activity_id', ''))
            body.append(f'    hmkia:generatedBy {act_uri} .')
            body.append('')
            layers[graph_uri] += body

    # Prepend each graph's own provenance description.
    out = {}
    for graph_uri, body in layers.items():
        act = None
        for a in activities:
            if _graph_name(edcs_id, a) == graph_uri:
                act = a
                break
        header = [f'  <{graph_uri}>', '    a prov:Entity ;']
        if act:
            header.append(
                f'    prov:wasGeneratedBy {_activity_uri(act.get("activity_id",""))} ;')
        if act and act.get('type') != 'extract' and extract_act:
            base = _graph_name(edcs_id, extract_act)
            header.append(f'    prov:wasDerivedFrom <{base}> ;')
        header.append(
            f'    epig:interpretsInscription '
            f'<http://epigraphic-careers.org/inscription/{_safe_id(edcs_id)}> .')
        header.append('')
        out[graph_uri] = header + body
    return out


def load_records(edcs_ids: set = None, sample: int = None) -> list:
    found = []
    for f in SRC.rglob('*_career.json'):
        try:
            data = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        for r in (data if isinstance(data, list) else [data]):
            eid = r.get('edcs_id')
            if not eid:
                continue
            if edcs_ids and eid not in edcs_ids:
                continue
            found.append(r)
            if sample and not edcs_ids and len(found) >= sample:
                return found
    return found


def count_current(record: dict) -> tuple:
    """Graphs/person-triples the CURRENT scheme produces for this record."""
    activities = record.get('_provenance', {}).get('activities', [])
    extract_act = next((a for a in activities if a.get('type') == 'extract'), None)
    triples = 0
    for person in record.get('persons', []):
        if person.get('person_name', '') in ('Parse Error', 'Error', 'No Text'):
            continue
        triples += 2  # rdf:type + surfaceForm
        for field in list(PERSON_FIELD_PREDICATE) + ['life_events']:
            triples += len(_person_value_lines(person, field))
    return (1 if extract_act else 0), triples


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('edcs_ids', nargs='*')
    ap.add_argument('--sample', type=int)
    ap.add_argument('--out', default='/tmp/prototype_layers.trig')
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args()

    records = load_records(set(args.edcs_ids) or None, args.sample)
    if not records:
        print('no records matched')
        return 1

    parts = []
    tot_new_g = tot_new_t = tot_old_g = tot_old_t = 0
    per_record = []

    for r in records:
        layers = build_layers(r)
        old_g, old_t = count_current(r)
        new_t = sum(1 for g in layers.values() for ln in g if ln.rstrip().endswith((';', '.')))
        tot_new_g += len(layers)
        tot_new_t += new_t
        tot_old_g += old_g
        tot_old_t += old_t
        per_record.append((r.get('edcs_id'), old_g, len(layers), old_t, new_t))
        for g, body in layers.items():
            parts.append(f'<{g}> {{')
            parts += body
            parts.append('}')
            parts.append('')

    Path(args.out).write_text('\n'.join(parts), encoding='utf-8')

    if not args.quiet:
        print(f'records: {len(records)}')
        print()
        print(f'{"edcs_id":<20} {"graphs(now)":>11} {"graphs(E)":>10} '
              f'{"triples(now)":>13} {"triples(E)":>11}')
        for row in per_record[:15]:
            print(f'{row[0]:<20} {row[1]:>11} {row[2]:>10} {row[3]:>13} {row[4]:>11}')
        if len(per_record) > 15:
            print(f'... and {len(per_record)-15} more')
    print()
    print(f'TOTAL graphs : {tot_old_g} -> {tot_new_g}'
          f'  ({tot_new_g/max(tot_old_g,1):.2f}x)')
    print(f'TOTAL triples: {tot_old_t} -> {tot_new_t}'
          f'  ({tot_new_t/max(tot_old_t,1):.2f}x)')
    print(f'written: {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
