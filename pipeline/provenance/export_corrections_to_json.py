#!/usr/bin/env python3
"""
Write human corrections held in Fuseki back into the career graph JSON.

apply_editor_json.py records a correction as a new editor graph in the triple
store, but the pipeline upstream of the store reads JSON, not SPARQL: both
enrich_career_graphs.py and create_rdf_himiko.py work from the career graph
files. Without this step a correction never reaches them, so the next
enrichment pass re-runs against the uncorrected value and the next re-ingest
publishes a machine graph that outranks the correction by timestamp. The
correction survives in its own graph but stops being the value readers see.

Writing it back makes the JSON the single source of truth. It also means the
existing "skip a field that already has a value" guard in the enrichment passes
starts protecting corrections for free.

The correction is also appended to the record's _provenance activities as a
manual_edit entry, so create_rdf_himiko.py attributes the value to the human
editor rather than silently folding it into the extract activity.

Usage:
    python provenance/export_corrections_to_json.py --dry-run
    python provenance/export_corrections_to_json.py --edcs-id EDCS-25501631
    python provenance/export_corrections_to_json.py --since 2026-10-01
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from apply_editor_json import Fuseki, HMKIA_NS, PROV_NS  # noqa: E402
from _provenance_utils import record_superseded_value  # noqa: E402

DEFAULT_ROOT = Path(__file__).parent / 'validated_career_graphs' / 'claude'

EPIG = 'http://epigraphic-careers.org/ontology#'
HMKI = 'urn:himiko:ontology:intrinsic:'

# RDF predicate -> JSON field, per resource kind. Mirrors the emission tables in
# create_rdf_himiko.py; a predicate absent here is not written back.
PERSON_FIELDS = {
    EPIG + 'personName':                       'person_name',
    EPIG + 'praenomen':                        'praenomen',
    EPIG + 'nomen':                            'nomen',
    EPIG + 'cognomen':                         'cognomen',
    EPIG + 'normalizedName':                   'person_name_normalized',
    EPIG + 'gender':                           'gender',
    EPIG + 'genderEvidence':                   'gender_evidence',
    EPIG + 'ethnicity':                        'ethnicity',
    EPIG + 'ethnicityEvidence':                'ethnicity_evidence',
    EPIG + 'socialStatus':                     'social_status',
    EPIG + 'socialStatusEvidence':             'social_status_evidence',
    EPIG + 'ageAtDeath':                       'age_at_death',
    EPIG + 'ageAtDeathEvidence':               'age_at_death_evidence',
    EPIG + 'isDivinity':                       'divinity',
    EPIG + 'divinityType':                     'divinity_type',
    EPIG + 'divinityClassificationReasoning':  'divinity_classification_reasoning',
    HMKI + 'surfaceForm':                      'person_name_readable',
}

COMMUNITY_FIELDS = {
    HMKI + 'surfaceForm':     'community_name',
    HMKI + 'normalizedForm':  'community_name_normalized',
    EPIG + 'communityType':   'community_type',
    EPIG + 'evidence':        'evidence',
}

CAREER_FIELDS = {
    EPIG + 'positionText':        'position',
    EPIG + 'positionNormalized':  'position_normalized',
    EPIG + 'positionType':        'position_type',
    EPIG + 'positionAbstract':    'position_abstract',
    EPIG + 'positionDescription': 'position_description',
}

BENEFACTION_FIELDS = {
    EPIG + 'benefactionType':    'benefaction_type',
    EPIG + 'objectText':         'object',
    EPIG + 'objectType':         'object_type',
    EPIG + 'costOriginalText':   'cost',
    EPIG + 'benefactionText':    'benefaction_text',
}

BOOL_FIELDS = {'divinity'}
INT_FIELDS = {'age_at_death'}

ENTITYREF_RE = re.compile(r'/entityref/(?P<edcs>[^/]+)/(?P<kind>person|community)/(?P<idx>\d+)$')
MK_RE = re.compile(r'/mk/(?P<edcs>[^/]+)/(?P<kind>career|benefaction|relationship)/(?P<idx>\d+)(?:_v\d+)?$')


def fetch_corrections(fuseki: Fuseki, edcs_id: str = None, since: str = None) -> list:
    """
    Return the current human-corrected value of every property a human touched.

    A property corrected more than once yields only its latest value: the query
    keeps the row whose act is newest, so re-running this script is idempotent.
    Human acts are identified by their agent being an hmkia:HumanAgent, the same
    test apply_editor_json.py uses — the graph name is not consulted.
    """
    filters = []
    if edcs_id:
        filters.append(f'FILTER(CONTAINS(STR(?subject), "/{edcs_id}/"))')
    if since:
        filters.append(f'FILTER(?t >= "{since}T00:00:00Z"^^'
                       f'<http://www.w3.org/2001/XMLSchema#dateTime>)')
    filter_block = '\n        '.join(filters)

    # Structural triples describe the version chain rather than carrying a
    # corrected value, so they are not write-back candidates.
    structural = ', '.join([
        f'<{HMKIA_NS}generatedBy>',
        '<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>',
        f'<{PROV_NS}wasRevisionOf>',
        f'<{PROV_NS}wasDerivedFrom>',
        f'<{PROV_NS}wasGeneratedBy>',
    ])

    # The human acts are bound first, inside a subquery, so the unbound
    # ?subject ?predicate ?value scan runs only against those few acts. Stating
    # the patterns in the other order lets the planner walk every triple in the
    # store that carries hmkia:generatedBy, which times out at this size.
    #
    # DISTINCT because the act's description and the agent's type may each sit
    # in more than one graph; without it every row multiplies by that count.
    rows = fuseki.select(f'''
        SELECT DISTINCT ?subject ?predicate ?value ?t ?editor WHERE {{
            {{
                SELECT DISTINCT ?act ?t ?editor WHERE {{
                    GRAPH ?gg {{ ?agent a <{HMKIA_NS}HumanAgent> }}
                    GRAPH ?ga {{ ?act <{PROV_NS}wasAssociatedWith> ?agent ;
                                      <{PROV_NS}generatedAtTime> ?t }}
                    OPTIONAL {{ GRAPH ?gl {{ ?agent
                        <http://www.w3.org/2000/01/rdf-schema#label> ?editor }} }}
                }}
            }}
            GRAPH ?g {{ ?subject <{HMKIA_NS}generatedBy> ?act ;
                                 ?predicate ?value }}
            FILTER(?predicate NOT IN ({structural}))
            {filter_block}
            FILTER NOT EXISTS {{
                GRAPH ?g2 {{ ?subject <{HMKIA_NS}generatedBy> ?act2 ;
                                      ?predicate ?v2 }}
                GRAPH ?ga2 {{ ?act2 <{PROV_NS}generatedAtTime> ?t2 ;
                                    <{PROV_NS}wasAssociatedWith> ?agent2 }}
                GRAPH ?gg2 {{ ?agent2 a <{HMKIA_NS}HumanAgent> }}
                FILTER(?t2 > ?t)
            }}
        }}
    ''')
    out = []
    for r in rows:
        out.append({
            'subject':   r['subject']['value'],
            'predicate': r['predicate']['value'],
            'value':     r['value']['value'],
            'datatype':  r['value'].get('datatype'),
            'timestamp': r['t']['value'],
            'editor':    r.get('editor', {}).get('value', 'unknown'),
        })
    return out


def _coerce(field: str, value: str, datatype: str):
    """Convert a SPARQL literal to the type the JSON field uses."""
    if field in BOOL_FIELDS:
        return str(value).lower() == 'true'
    if field in INT_FIELDS:
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    return value


def _career_entries(record: dict) -> list:
    """
    career_path dicts in the order create_rdf_himiko.py numbers them.

    That order is what mk/<id>/career/<i> means, so it has to be reproduced
    exactly: persons in record order, skipping those without has_career, and
    each person's career_path sorted by 'order'.
    """
    out = []
    for person in record.get('persons', []):
        if person.get('person_name', '') in ('Parse Error', 'Error', 'No Text'):
            continue
        if not person.get('has_career'):
            continue
        path = person.get('career_path', [])
        if path and isinstance(path[0], dict):
            out.extend(sorted(path, key=lambda x: x.get('order', 0)))
        else:
            out.extend({'position': p, 'order': i} for i, p in enumerate(path))
    return out


def _benefaction_entries(record: dict) -> list:
    """benefaction dicts in emission order (persons first, then communities)."""
    out = []
    for person in record.get('persons', []):
        if person.get('person_name', '') in ('Parse Error', 'Error', 'No Text'):
            continue
        out.extend(person.get('benefactions', []) or [])
    for community in record.get('communities', []):
        out.extend(community.get('benefactions', []) or [])
    return out


def locate_target(record: dict, subject: str) -> tuple:
    """
    Resolve a correction's subject URI to (container_dict, field_map, label).

    Returns (None, None, reason) when the URI does not address anything in this
    record — a statement index past the end, for instance, which happens if the
    JSON changed shape after the correction was made.
    """
    m = ENTITYREF_RE.search(subject)
    if m:
        idx = int(m.group('idx'))
        if m.group('kind') == 'person':
            for p in record.get('persons', []):
                if p.get('person_id') == idx:
                    return p, PERSON_FIELDS, f'person/{idx}'
            return None, None, f'no person with person_id={idx}'
        for c in record.get('communities', []):
            if c.get('community_id') == idx:
                return c, COMMUNITY_FIELDS, f'community/{idx}'
        return None, None, f'no community with community_id={idx}'

    m = MK_RE.search(subject)
    if m:
        idx = int(m.group('idx'))
        kind = m.group('kind')
        if kind == 'career':
            entries = _career_entries(record)
            if idx < len(entries):
                return entries[idx], CAREER_FIELDS, f'career[{idx}]'
            return None, None, f'career index {idx} out of range ({len(entries)})'
        if kind == 'benefaction':
            entries = _benefaction_entries(record)
            if idx < len(entries):
                return entries[idx], BENEFACTION_FIELDS, f'benefaction[{idx}]'
            return None, None, f'benefaction index {idx} out of range ({len(entries)})'
        return None, None, f'{kind} corrections are not written back'

    return None, None, 'unrecognised subject URI'


def manual_edit_activity_id(corrections: list) -> str:
    """
    Activity id for the manual_edit act covering these corrections.

    One act per record rather than per edit, named for its editors and the
    latest timestamp among them, so repeated exports of the same corrections
    produce the same id and overwrite rather than accumulate.
    """
    latest = max(c['timestamp'] for c in corrections)
    editors = sorted({c['editor'] for c in corrections})
    ts = latest.replace('-', '').replace(':', '')
    return f'apply_editor_json-manual_edit-{"-".join(editors)}-{ts}'


def record_manual_edit_activity(record: dict, corrections: list) -> None:
    """
    Add one manual_edit activity listing the fields a human set.

    Kept in the same shape as the enrich activities so create_rdf_himiko.py's
    _act_uri_for_field() can attribute those fields to the editor. Replaced
    rather than appended on re-run, so repeated exports do not pile up.

    Inserted at the front of the list because _act_uri_for_field() returns the
    first activity claiming a field, and extract claims nearly all person
    fields. Appending would leave a corrected value credited to extract.
    """
    fields = sorted({c['_field_label'] for c in corrections})
    latest = max(c['timestamp'] for c in corrections)
    editors = sorted({c['editor'] for c in corrections})

    activity = {
        'activity_id': manual_edit_activity_id(corrections),
        'script': 'apply_editor_json.py',
        'type': 'manual_edit',
        'model_id': None,
        'editor': ', '.join(editors),
        'timestamp': latest,
        'generated_fields': fields,
    }
    record.setdefault('_provenance', {'activities': []})
    acts = [a for a in record['_provenance'].get('activities', [])
            if a.get('type') != 'manual_edit']
    acts.insert(0, activity)
    record['_provenance']['activities'] = acts


def apply_to_record(record: dict, corrections: list, verbose: bool) -> tuple:
    """Apply corrections to one record. Returns (applied, skipped)."""
    applied, skipped = [], []
    # All of this record's corrections are attributed to one act, so the id is
    # fixed before any value is replaced and reused for every history entry.
    act_id = manual_edit_activity_id(corrections)

    for corr in corrections:
        target, field_map, label = locate_target(record, corr['subject'])
        if target is None:
            skipped.append((corr, label))
            continue
        field = (field_map or {}).get(corr['predicate'])
        if not field:
            skipped.append((corr, f'predicate not mapped: {corr["predicate"]}'))
            continue

        new_value = _coerce(field, corr['value'], corr['datatype'])
        old_value = target.get(field)
        if old_value == new_value:
            continue

        corr['_field_label'] = (
            'persons[].' + field if field_map is PERSON_FIELDS else
            'communities[].' + field if field_map is COMMUNITY_FIELDS else
            'career_path[].' + field if field_map is CAREER_FIELDS else
            'benefactions[].' + field
        )

        # Preserve what the correction displaces. Without this the prior value
        # is gone from the JSON, and the next RDF generation rewrites the same
        # named graph with the corrected value, erasing it from the store too.
        record_superseded_value(
            record,
            path=f'{label}.{field}',
            field_label=corr['_field_label'],
            old_value=old_value,
            superseded_by={'activity_id': act_id},
            superseded_at=corr['timestamp'],
        )

        target[field] = new_value
        applied.append((corr, label, field, old_value, new_value))
        if verbose:
            print(f'      {label}.{field}: {old_value!r} -> {new_value!r}')

    if applied:
        record_manual_edit_activity(record, [c for c, *_ in applied])
    return applied, skipped


def main() -> int:
    ap = argparse.ArgumentParser(
        description='Write human corrections from Fuseki back into career graph JSON')
    ap.add_argument('--endpoint', default='http://54.92.185.36/himiko_epigraphy')
    ap.add_argument('--root', default=str(DEFAULT_ROOT),
                    help='career graph JSON directory')
    ap.add_argument('--edcs-id', help='restrict to one inscription')
    ap.add_argument('--since', help='only corrections on/after this date (YYYY-MM-DD)')
    ap.add_argument('--dry-run', action='store_true',
                    help='report what would change without writing files')
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args()

    fuseki = Fuseki(args.endpoint)
    corrections = fetch_corrections(fuseki, args.edcs_id, args.since)
    if not corrections:
        print('No human corrections found in the store.')
        return 0

    by_edcs = defaultdict(list)
    for c in corrections:
        m = ENTITYREF_RE.search(c['subject']) or MK_RE.search(c['subject'])
        if m:
            by_edcs[m.group('edcs')].append(c)
    print(f'{len(corrections)} correction(s) across {len(by_edcs)} inscription(s)')
    print()

    root = Path(args.root)
    total_applied = total_skipped = files_changed = 0
    unmatched = set(by_edcs)

    for path in sorted(root.rglob('*_career.json')):
        try:
            data = json.load(open(path, encoding='utf-8'))
        except Exception as e:
            print(f'  WARN unreadable {path.name}: {e}')
            continue
        records = data if isinstance(data, list) else [data]

        changed = False
        for record in records:
            eid = record.get('edcs_id')
            if eid not in by_edcs:
                continue
            unmatched.discard(eid)
            if not args.quiet:
                print(f'  {eid}  ({path.relative_to(root)})')
            applied, skipped = apply_to_record(record, by_edcs[eid],
                                               not args.quiet)
            for corr, reason in skipped:
                subj = corr['subject'].rsplit('/', 2)[-2:]
                pred = corr['predicate'].split('#')[-1].rsplit('/', 1)[-1]
                print(f'      SKIP {"/".join(subj)} {pred}: {reason}')
            total_applied += len(applied)
            total_skipped += len(skipped)
            if applied:
                changed = True

        if changed and not args.dry_run:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            files_changed += 1
        elif changed:
            files_changed += 1

    print()
    if unmatched:
        print(f'WARNING: no JSON record found for: {", ".join(sorted(unmatched))}')
    print(f'Applied : {total_applied}')
    print(f'Skipped : {total_skipped}')
    print(f'Files   : {files_changed}' + ('  (dry run, nothing written)'
                                          if args.dry_run else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
