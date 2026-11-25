"""
Shared utilities for _provenance metadata generation.

Each pipeline script in provenance/ calls these functions to attach
_provenance.activities to JSON records before writing output.

PROV-O mapping:
  activity_id  → <activity/{activity_id}>  (prov:Activity URI)
  script       → prov:wasAssociatedWith / epig:script
  model_id     → prov:wasAssociatedWith <agent/{model_id}>
  date         → prov:generatedAtTime
  generated_fields → basis for RDF-star annotations per triple
  value_history    → superseded values, emitted as a history graph
"""

from datetime import datetime, timezone
from pathlib import Path


# ── Model ID constants ────────────────────────────────────────────────────────

MODEL_IDS = {
    'claude':   'claude-sonnet-4-6',
    'gemini':   'gemini-3-pro-preview',
    'gpt':      'gpt-5.2-2025-12-11',
    'gpt-oss':  'gpt-oss:120b',
    'qwen3.5':  'qwen3.5:35b',
    'gemma4':   'gemma4:31b',
}


# ── Field ownership tables ────────────────────────────────────────────────────

EXTRACT_PERSON_FIELDS = [
    'person_id', 'person_name', 'person_name_readable',
    'praenomen', 'nomen', 'cognomen',
    'person_name_normalized', 'person_name_link',
    'social_status', 'social_status_evidence',
    'gender', 'gender_evidence',
    'ethnicity', 'ethnicity_evidence',
    'age_at_death', 'age_at_death_evidence',
    'has_career',
]

EXTRACT_CAREER_FIELDS = [
    'position', 'position_normalized', 'position_abstract',
    'position_type', 'position_description', 'order',
    'location', 'location_normalized', 'location_evidence',
]

EXTRACT_BENEFACTION_FIELDS = [
    'benefaction_type', 'object', 'object_type', 'object_description',
    'objects', 'benefaction_text', 'cost', 'notes',
]

EXTRACT_RECORD_FIELDS = [
    'communities', 'person_relationships', 'notes',
]

# Each tuple: (group_key, detector_fn, field_labels)
ENRICH_GROUPS = [
    (
        'divinity',
        lambda r: any('divinity' in p for p in r.get('persons', [])),
        ['persons[].divinity', 'persons[].divinity_type',
         'persons[].divinity_classification_reasoning'],
    ),
    (
        'vital_events',
        lambda r: any('life_events' in p for p in r.get('persons', [])),
        ['persons[].life_events'],
    ),
    (
        'cost',
        lambda r: any(
            'cost_numeric' in b
            for p in r.get('persons', [])
            for b in p.get('benefactions', [])
        ),
        ['benefactions[].cost_numeric', 'benefactions[].cost_unit',
         'benefactions[].cost_original', 'benefactions[].cost_conversion_reasoning'],
    ),
    (
        'career_location',
        lambda r: any(
            'location' in cp
            for p in r.get('persons', [])
            for cp in p.get('career_path', [])
        ),
        ['career_path[].location', 'career_path[].location_normalized',
         'career_path[].location_evidence'],
    ),
    (
        'benef_objects',
        lambda r: any(
            'objects' in b
            for p in r.get('persons', [])
            for b in p.get('benefactions', [])
        ),
        ['benefactions[].objects'],
    ),
    (
        'benef_recipients',
        lambda r: any(
            'recipient_communities' in b
            for p in r.get('persons', [])
            for b in p.get('benefactions', [])
        ),
        ['benefactions[].recipient_communities'],
    ),
    (
        'comm_benefactions',
        lambda r: any('benefactions' in c for c in r.get('communities', [])),
        ['communities[].benefactions'],
    ),
]

SCHEMA_FIX_PERSON_FIELDS = [
    'ethnicity', 'ethnicity_evidence',
    'person_name_normalized', 'person_name_link',
    'age_at_death', 'age_at_death_evidence',
]

SCHEMA_FIX_RELATIONSHIP_FIELDS = [
    'target_community_id', 'notes',
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def now_iso() -> str:
    """Return current UTC datetime as ISO 8601 string."""
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def make_activity_id(script: str, group: str, model_id: str, timestamp: str) -> str:
    """
    Build a URL-safe activity_id usable as prov:Activity URI.
    e.g. "extract_career_graph-extract-claude-sonnet-4-5-20250929-20260419T120000Z"
    """
    ts_compact = timestamp.replace(':', '').replace('-', '')
    model_safe = model_id.replace(' ', '-')
    script_stem = Path(script).stem
    parts = [script_stem]
    if group:
        parts.append(group)
    parts += [model_safe, ts_compact]
    return '-'.join(parts)


def extract_fields_list() -> list:
    return sorted(
        ['persons[].' + f for f in EXTRACT_PERSON_FIELDS]
        + ['career_path[].' + f for f in EXTRACT_CAREER_FIELDS]
        + ['benefactions[].' + f for f in EXTRACT_BENEFACTION_FIELDS]
        + EXTRACT_RECORD_FIELDS
    )


def schema_fix_fields_list() -> list:
    return sorted(
        ['persons[].' + f for f in SCHEMA_FIX_PERSON_FIELDS]
        + ['person_relationships[].' + f for f in SCHEMA_FIX_RELATIONSHIP_FIELDS]
    )


# ── Activity builders ─────────────────────────────────────────────────────────

def make_extract_activity(model_type: str, timestamp: str) -> dict:
    """Build the extract prov:Activity entry."""
    model_id = MODEL_IDS.get(model_type, model_type)
    return {
        'activity_id': make_activity_id(
            'extract_career_graph.py', 'extract', model_id, timestamp),
        'script': 'extract_career_graph.py',
        'type': 'extract',
        'model_type': model_type,
        'model_id': model_id,
        'timestamp': timestamp,
        'generated_fields': extract_fields_list(),
    }


def make_enrich_activity(group_key: str, field_labels: list,
                         model_id: str, timestamp: str) -> dict:
    """Build one enrich prov:Activity entry."""
    return {
        'activity_id': make_activity_id(
            'enrich_career_graphs.py', group_key, model_id, timestamp),
        'script': 'enrich_career_graphs.py',
        'type': f'enrich_{group_key}',
        'model_id': model_id,
        'timestamp': timestamp,
        'generated_fields': field_labels,
    }


def make_schema_fix_activity(timestamp: str) -> dict:
    """Build the schema_fix prov:Activity entry (no LLM model)."""
    return {
        'activity_id': make_activity_id(
            'fix_and_export.py', 'schema_fix', 'none', timestamp),
        'script': 'validation/fix_and_export.py',
        'type': 'schema_fix',
        'model_id': None,
        'timestamp': timestamp,
        'generated_fields': schema_fix_fields_list(),
    }


# ── Record-level provenance attachment ───────────────────────────────────────

def attach_extract_provenance(record: dict, model_type: str, timestamp: str) -> dict:
    """
    Attach (or initialise) _provenance with an extract activity.
    Returns the record with _provenance set.
    """
    activity = make_extract_activity(model_type, timestamp)
    record.setdefault('_provenance', {'activities': []})
    # Replace any existing extract activity for idempotency
    acts = record['_provenance']['activities']
    acts = [a for a in acts if a.get('type') != 'extract']
    acts.insert(0, activity)
    record['_provenance']['activities'] = acts
    return record


def attach_enrich_provenance(record: dict, group_key: str, field_labels: list,
                             model_id: str, timestamp: str) -> dict:
    """
    Append (or replace) one enrich activity in _provenance.
    Called immediately after each enrich group writes its fields.
    """
    activity = make_enrich_activity(group_key, field_labels, model_id, timestamp)
    record.setdefault('_provenance', {'activities': []})
    acts = record['_provenance']['activities']
    activity_type = f'enrich_{group_key}'
    acts = [a for a in acts if a.get('type') != activity_type]
    acts.append(activity)
    record['_provenance']['activities'] = acts
    return record


def attach_schema_fix_provenance(record: dict, timestamp: str) -> dict:
    """Append schema_fix activity to _provenance."""
    activity = make_schema_fix_activity(timestamp)
    record.setdefault('_provenance', {'activities': []})
    acts = record['_provenance']['activities']
    acts = [a for a in acts if a.get('type') != 'schema_fix']
    acts.append(activity)
    record['_provenance']['activities'] = acts
    return record


# ── Value history ─────────────────────────────────────────────────────────────

def _field_owner_activity(record: dict, field_label: str) -> dict:
    """
    Return the activity that last claimed field_label, or None.

    Mirrors create_rdf_himiko._act_uri_for_field(): the first activity listing
    the field in generated_fields owns it. Used to attribute a superseded value
    to whichever act produced it, not to whichever act replaced it.
    """
    for act in record.get('_provenance', {}).get('activities', []):
        if field_label in act.get('generated_fields', []):
            return act
    return None


def record_superseded_value(record: dict, path: str, field_label: str,
                            old_value, superseded_by: dict,
                            superseded_at: str) -> bool:
    """
    Preserve a value that is about to be overwritten.

    The career graph JSON has no notion of versions: extract, each enrichment
    pass and the editor all assign to the same key, so the prior value is lost
    the moment it is replaced. Statements survive this because they are emitted
    as _vN chains, but EntityReference attributes (person/community fields) are
    emitted once per inscription and would simply change. Re-ingesting then
    rewrites the same named graph, erasing the earlier value from the store too.

    Appending to _provenance.value_history keeps the old value in the working
    format, which lets create_rdf_himiko.py emit it into an append-only history
    graph. Only EntityReference-level fields need this; statement fields are
    already versioned.

    path identifies the JSON location (persons[1].cognomen) so the entry can be
    traced back; field_label is the generated_fields form (persons[].cognomen)
    used to find the activity that produced the value.

    Returns True if an entry was added.
    """
    if old_value is None or old_value == '' or old_value == []:
        return False

    producer = _field_owner_activity(record, field_label)
    entry = {
        'path':          path,
        'field':         field_label,
        'value':         old_value,
        'generated_by':  (producer or {}).get('activity_id'),
        'generated_at':  (producer or {}).get('timestamp'),
        'superseded_at': superseded_at,
        'superseded_by': (superseded_by or {}).get('activity_id'),
    }

    prov = record.setdefault('_provenance', {'activities': []})
    history = prov.setdefault('value_history', [])

    # Re-running an export must not duplicate entries: the same value
    # superseded by the same act at the same path is already recorded.
    for existing in history:
        if (existing.get('path') == entry['path']
                and existing.get('value') == entry['value']
                and existing.get('superseded_by') == entry['superseded_by']):
            return False

    history.append(entry)
    return True


# ── Value fingerprints (assessment status) ────────────────────────────────────
#
# An assessment (LLM judge, human review, manual edit) is tied to the value it
# looked at, not to an RDF URI: statement URIs are positional and can point to
# different content after a rebuild. The writers record these fingerprints and
# compute_assessment_status.py compares them with the current values.
# See docs/ASSESSMENT_STATUS_SPEC.md.

def field_fingerprint(value) -> str:
    """12-hex fingerprint of one JSON value (canonical JSON, keys sorted)."""
    import hashlib
    import json
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]


def leaf_fingerprints(value, path: str) -> dict:
    """{leaf path: fingerprint} for every scalar under `value` at `path`.

    Paths use the judge/edit notation: persons[0].career_path[2].position_tier.
    An empty list or object is recorded as a leaf of its own.
    """
    out = {}

    def walk(v, p):
        if isinstance(v, dict) and v:
            for k, sub in v.items():
                walk(sub, f'{p}.{k}')
        elif isinstance(v, list) and v:
            for i, sub in enumerate(v):
                walk(sub, f'{p}[{i}]')
        else:
            out[p] = field_fingerprint(v)

    walk(value, path)
    return out
