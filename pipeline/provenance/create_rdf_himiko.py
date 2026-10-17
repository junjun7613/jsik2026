#!/usr/bin/env python3
"""
HIMIKO-aligned RDF generation from provenance-annotated career graph JSON.

Generates TriG output with HIMIKO upper ontology alignment:
  - graph/{id}/edcs/...   : hmkp:Source (史料物理層)
  - graph/{id}/claude/... : hmki:EntityReference + epig:*Statement (史料内在知識層)
  - graph/provenance      : hmkia:InterpretationAct + hmkia:Agent (解釈行為層)

InterpretationAct は CreationAct / UpdateAct で型付けされる。
UpdateAct は hmkia:revises で先行 Act を参照する。
Statement はバージョン付き URI (_v0, _v1, ...) を持ち、
UpdateAct が生成したバージョンは prov:wasRevisionOf で前バージョンを参照する。

All resource URIs are written as full IRIs <http://...> — no prefixed names for
resources containing slashes or hyphens (TriG parser restriction).

Usage:
    python provenance/create_rdf_himiko.py --model claude
    python provenance/create_rdf_himiko.py --model claude --places "Dougga_Thugga"
    python provenance/create_rdf_himiko.py --model claude --merge
"""

import json
import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
PIPELINE_DIR = SCRIPT_DIR.parent
INPUT_DIR = SCRIPT_DIR / 'validated_career_graphs'
OUTPUT_DIR = SCRIPT_DIR / 'rdf_output_himiko'

# ── Pleiades mapping ──────────────────────────────────────────────────────────

def _load_pleiades_mapping() -> dict:
    path = PIPELINE_DIR / 'place_pleiades_mapping.json'
    if path.exists():
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return {}

PLEIADES_MAP: dict = {}  # populated in main()
SIRAR_MAP: dict = {}     # populated in main()

def _load_sirar_mapping() -> dict:
    import csv
    path = PIPELINE_DIR / 'external' / 'sirar_edcs_mapping.csv'
    result = {}
    if path.exists():
        with open(path, encoding='utf-8') as f:
            for row in csv.DictReader(f):
                edcs_id = row.get('edcs_id', '').strip()
                if edcs_id:
                    result[edcs_id] = {
                        'sirar_id': row['sirar_id'].strip(),
                        'sirar_url': row['sirar_url'].strip(),
                    }
    return result

# ── Namespace bases ───────────────────────────────────────────────────────────

BASE         = 'http://epigraphic-careers.org/'
EPIG_NS      = BASE + 'ontology#'
EPIGF_NS     = BASE + 'ontology/funding/'
EPIGO_NS     = BASE + 'ontology/object/'
EPIGS_NS     = BASE + 'ontology/status/'
EPIGP_NS     = BASE + 'ontology/position/'
ACTIVITY_NS  = BASE + 'activity/'
AGENT_NS     = BASE + 'agent/'
GRAPH_NS     = BASE + 'graph/'
INSC_NS      = BASE + 'inscription/'
ENTITYREF_NS = BASE + 'entityref/'
MK_NS        = BASE + 'mk/'
PROVINCE_NS  = BASE + 'province/'
PLACE_NS     = BASE + 'place/'

HMKP_NS    = 'urn:himiko:ontology:physical:'
HMKI_NS    = 'urn:himiko:ontology:intrinsic:'
HMKE_NS    = 'urn:himiko:ontology:extrinsic:'
HMKIA_NS   = 'urn:himiko:ontology:interpretation:'
ENTITY_NS  = BASE + 'entity/'
PROV_NS    = 'http://www.w3.org/ns/prov#'
XSD_NS     = 'http://www.w3.org/2001/XMLSchema#'
RDFS_NS    = 'http://www.w3.org/2000/01/rdf-schema#'
PLEIADES_NS = 'https://pleiades.stoa.org/places/'
EXTDB_NS   = BASE + 'external-link/'
SCHEMA_NS  = 'https://schema.org/'

# ── TriG prefix block ─────────────────────────────────────────────────────────
# Only simple prefixes whose local parts never contain slashes or hyphens.

PREFIXES = f"""\
@prefix epig:   <{EPIG_NS}> .
@prefix epigo:  <{EPIGO_NS}> .
@prefix epigs:  <{EPIGS_NS}> .
@prefix epigp:  <{EPIGP_NS}> .
@prefix hmkp:   <{HMKP_NS}> .
@prefix hmki:   <{HMKI_NS}> .
@prefix hmke:   <{HMKE_NS}> .
@prefix hmkia:  <{HMKIA_NS}> .
@prefix prov:   <{PROV_NS}> .
@prefix xsd:    <{XSD_NS}> .
@prefix rdfs:   <{RDFS_NS}> .
@prefix owl:    <http://www.w3.org/2002/07/owl#> .
@prefix pleiad: <{PLEIADES_NS}> .
@prefix schema: <{SCHEMA_NS}> .
"""


# epig:positionType は 2026-10-17 に xsd:string から epig:PositionType へ
# range を変更した。JSON 側は文字列のままなので、ここで URI に写像する。
# ハイフンは URI のローカル名に使えるがアンダースコアに揃える
# （epigp:imperial_administration）。
def _position_type_uri(value: str) -> str:
    return f'<{EPIGP_NS}{value.strip().replace("-", "_")}>'


# ── Serialisation helpers ─────────────────────────────────────────────────────

def _esc(s: str) -> str:
    return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')


def _lit(value, datatype: str = None) -> str:
    if datatype:
        return f'"{_esc(str(value))}"^^<{datatype}>'
    return f'"{_esc(str(value))}"'


def _int_lit(v) -> str:
    return f'"{int(v)}"^^<{XSD_NS}integer>'


def _dt_lit(ts: str) -> str:
    return f'"{ts}"^^<{XSD_NS}dateTime>'


def _safe_id(s: str) -> str:
    return re.sub(r'[^\w.\-]', '_', str(s))


def _insc(edcs_id: str) -> str:
    return f'<{INSC_NS}{_safe_id(edcs_id)}>'


def _eref_person(edcs_id: str, person_id) -> str:
    return f'<{ENTITYREF_NS}{_safe_id(edcs_id)}/person/{person_id}>'


def _eref_community(edcs_id: str, community_id) -> str:
    return f'<{ENTITYREF_NS}{_safe_id(edcs_id)}/community/{community_id}>'


def _mk_career(edcs_id: str, i: int, version: int = 0) -> str:
    return f'<{MK_NS}{_safe_id(edcs_id)}/career/{i}_v{version}>'


def _mk_benefaction(edcs_id: str, i: int, version: int = 0) -> str:
    return f'<{MK_NS}{_safe_id(edcs_id)}/benefaction/{i}_v{version}>'


def _mk_relationship(edcs_id: str, i: int, version: int = 0) -> str:
    return f'<{MK_NS}{_safe_id(edcs_id)}/relationship/{i}_v{version}>'


def _activity_uri(act_id: str) -> str:
    return f'<{ACTIVITY_NS}{_safe_id(act_id)}>'


def _agent_uri(model_id: str) -> str:
    return f'<{AGENT_NS}{_safe_id(model_id)}>'


def _close(lines: list) -> None:
    """Replace trailing ' ;' with ' .' on the last substantive line."""
    if lines and lines[-1].endswith(' ;'):
        lines[-1] = lines[-1][:-2] + ' .'


# ── Activity helpers ──────────────────────────────────────────────────────────

def _collect_activities(data: list) -> dict:
    """Return {activity_id: activity_dict} deduplicated across all records."""
    result = {}
    for record in data:
        for act in record.get('_provenance', {}).get('activities', []):
            aid = act.get('activity_id', '')
            if aid and aid not in result:
                result[aid] = act
    return result


_CREATION_TYPES = {'extract', 'reextract_relationships'}


def _is_creation_act(act: dict) -> bool:
    return act.get('type', '') in _CREATION_TYPES


def _extract_act(activities: dict) -> tuple[str, str]:
    """Return (activity_id, date_str) of the first extract activity."""
    for act_id, act in activities.items():
        if act.get('type') == 'extract':
            ts = act.get('timestamp') or act.get('date') or ''
            date = ts[:10] if ts else ''
            return act_id, date
    return '', ''


def _ordered_acts(activities: list) -> list[dict]:
    """Return activities sorted by timestamp (creation acts first, then update acts)."""
    def _ts(a):
        return a.get('timestamp') or a.get('date') or ''
    creation = sorted([a for a in activities if _is_creation_act(a)], key=_ts)
    updates  = sorted([a for a in activities if not _is_creation_act(a)], key=_ts)
    return creation + updates


def _act_uri_for_type(activities: list, act_type: str) -> str | None:
    """Return the URI of the first activity matching act_type in a record's activity list."""
    for act in activities:
        if act.get('type') == act_type:
            aid = act.get('activity_id', '')
            if aid:
                return _activity_uri(aid)
    return None


def _act_uri_for_field(activities: list, field_path: str) -> str | None:
    """Return activity URI for the activity that generated a specific field."""
    for act in activities:
        if field_path in act.get('generated_fields', []):
            aid = act.get('activity_id', '')
            if aid:
                return _activity_uri(aid)
    return None


# ── Provenance graph ──────────────────────────────────────────────────────────

def build_provenance_graph(all_activities: dict,
                           researchers: 'list[dict]' = None) -> list[str]:
    """Build the shared <graph/provenance> TriG block as a list of lines.

    researchers: list of dicts with keys:
        uri   – project-internal URI string (e.g. 'http://.../agent/person/researcher-0')
        name  – display name string
        orcid – optional ORCID URI string (e.g. 'https://orcid.org/0000-...')
    """
    researchers = researchers or []
    lines = [f'<{GRAPH_NS}provenance> {{', '']

    # Determine the creation act to use as revises target for the first update act.
    # For each update act, revises the most recent preceding act by timestamp.
    acts_sorted = sorted(all_activities.values(),
                         key=lambda a: a.get('timestamp') or a.get('date') or '')
    # Build preceding-act map: act_id -> act_id of the act immediately before it
    _preceding: dict[str, str] = {}
    for idx, act in enumerate(acts_sorted):
        if idx > 0:
            _preceding[act['activity_id']] = acts_sorted[idx - 1]['activity_id']

    for act_id, act in sorted(all_activities.items()):
        act_uri = _activity_uri(act_id)
        lines.append(f'  {act_uri}')

        if _is_creation_act(act):
            lines.append(f'    a hmkia:InterpretationCreationAct ;')
        else:
            lines.append(f'    a hmkia:InterpretationUpdateAct ;')

        script = act.get('script', '')
        if script:
            lines.append(f'    epig:script {_lit(script)} ;')

        act_type = act.get('type', '')
        if act_type:
            lines.append(f'    epig:activityType {_lit(act_type)} ;')
            lines.append(f'    hmkia:hasType {_lit(act_type)} ;')

        model_id = act.get('model_id') or act.get('model') or ''

        # prov:wasAssociatedWith shortcut triples (software + all researchers)
        if model_id and model_id != 'none':
            lines.append(f'    prov:wasAssociatedWith {_agent_uri(model_id)} ;')
        for r in researchers:
            lines.append(f'    prov:wasAssociatedWith <{r["uri"]}> ;')

        # prov:qualifiedAssociation — software as executor
        if model_id and model_id != 'none':
            lines.append(f'    prov:qualifiedAssociation [')
            lines.append(f'        a prov:Association ;')
            lines.append(f'        prov:agent {_agent_uri(model_id)} ;')
            lines.append(f'        prov:hadRole hmkia:ExecutorRole')
            lines.append(f'    ] ;')

        # prov:qualifiedAssociation — each researcher as responsible party
        for r in researchers:
            lines.append(f'    prov:qualifiedAssociation [')
            lines.append(f'        a prov:Association ;')
            lines.append(f'        prov:agent <{r["uri"]}> ;')
            lines.append(f'        prov:hadRole hmkia:ResponsiblePartyRole')
            lines.append(f'    ] ;')

        ts = act.get('timestamp') or act.get('date') or ''
        if ts:
            if 'T' in ts:
                lines.append(f'    hmkia:hasDate {_dt_lit(ts)} ;')
                lines.append(f'    prov:generatedAtTime {_dt_lit(ts)} ;')
            else:
                lines.append(f'    hmkia:hasDate "{ts}"^^<{XSD_NS}date> ;')
                lines.append(f'    prov:generatedAtTime "{ts}"^^<{XSD_NS}date> ;')

        # UpdateAct: link to the act it revises
        if not _is_creation_act(act) and act_id in _preceding:
            prev_uri = _activity_uri(_preceding[act_id])
            lines.append(f'    hmkia:revises {prev_uri} ;')

        _close(lines)
        lines.append('')

    # Software agent nodes
    seen_agents: set = set()
    for act in all_activities.values():
        model_id = act.get('model_id') or act.get('model') or ''
        if model_id and model_id != 'none' and model_id not in seen_agents:
            seen_agents.add(model_id)
            lines.append(f'  {_agent_uri(model_id)}')
            lines.append(f'    a hmkia:SoftwareAgent , prov:SoftwareAgent ;')
            lines.append(f'    hmkia:agentName {_lit(model_id)} ;')
            lines.append(f'    rdfs:label {_lit(model_id)} .')
            lines.append('')

    # Human agent nodes
    for r in researchers:
        lines.append(f'  <{r["uri"]}>')
        lines.append(f'    a hmkia:HumanAgent , prov:Person ;')
        lines.append(f'    hmkia:agentName {_lit(r["name"])} ;')
        lines.append(f'    rdfs:label {_lit(r["name"])} ;')
        if r.get('orcid'):
            lines.append(f'    owl:sameAs <{r["orcid"]}> ;')
        _close(lines)
        lines.append('')

    lines.append('}')
    return lines


def build_entity_links(record: dict, llm_date: str, scrape_date: str,
                       extract_act_id: str) -> list[str]:
    """Return prov:Entity triples linking LLM graph to EDCS graph.

    prov:wasGeneratedBy  → the extract (creation) activity
    prov:wasInfluencedBy → every subsequent enrich / reextract activity,
                           so SPARQL can find all activities that touched
                           this graph without traversing statement-level triples.
    """
    edcs_id = record.get('edcs_id', 'Unknown')
    llm_graph  = f'<{GRAPH_NS}{edcs_id}/claude/{llm_date}>'
    edcs_graph = f'<{GRAPH_NS}{edcs_id}/edcs/{scrape_date}>'
    insc_uri   = _insc(edcs_id)

    # The EDCS graph is described regardless of whether an LLM extraction ran:
    # it is the scrape of the source database, independent of interpretation.
    # Inscription metadata (dating, findspot …) lives there and needs a
    # generation time to be orderable against later corrections.
    scrape_act_uri = f'<{ACTIVITY_NS}scrape_edcs-{_safe_id(scrape_date)}>'
    edcs_lines = [
        f'  {edcs_graph}',
        f'    a prov:Entity ;',
        f'    prov:wasGeneratedBy {scrape_act_uri} ;',
        f'    epig:interpretsInscription {insc_uri} .',
        '',
        f'  {scrape_act_uri}',
        f'    a <{HMKIA_NS}InterpretationCreationAct> ;',
        f'    <{HMKIA_NS}hasType> "scrape_edcs" ;',
        f'    <{HMKIA_NS}hasDate> "{scrape_date}"^^xsd:date ;',
        f'    epig:activityType "scrape_edcs" ;',
        f'    epig:script "batch_scrape_new_edcs.py" ;',
        f'    prov:generatedAtTime "{scrape_date}T00:00:00Z"^^xsd:dateTime .',
        '',
    ]

    if not extract_act_id:
        return edcs_lines

    act_uri = _activity_uri(extract_act_id)
    lines = [
        f'  {llm_graph}',
        f'    a prov:Entity ;',
        f'    prov:wasGeneratedBy {act_uri} ;',
    ]

    # Add prov:wasInfluencedBy for every non-extract activity in this record
    activities = record.get('_provenance', {}).get('activities', [])
    for act in activities:
        aid = act.get('activity_id', '')
        if aid and aid != extract_act_id:
            lines.append(f'    prov:wasInfluencedBy {_activity_uri(aid)} ;')

    lines += [
        f'    prov:wasDerivedFrom {edcs_graph} ;',
        f'    epig:interpretsInscription {insc_uri} .',
        '',
    ]

    return lines + edcs_lines


# ── Source graph (史料物理層) ──────────────────────────────────────────────────

def build_source_graph(record: dict, scrape_date: str,
                       career_latest: list[str],
                       benefaction_latest: list[str],
                       relationship_latest: list[str],
                       community_uris: list[str]) -> list[str]:
    """Build the EDCS/source TriG block (hmkp:Source + hmkp:mentions links).

    career_latest / benefaction_latest / relationship_latest are lists of the
    most-recent-version URIs for each statement slot, as returned by the
    _build_*_statements functions.  hmkp:mentions always points to the latest
    version so clients need no prov:wasRevisionOf path traversal.
    community_uris are entityref URIs for all communities in the record.
    """
    edcs_id = record.get('edcs_id', 'Unknown')
    orig = record.get('original_data', {})
    graph_uri = f'<{GRAPH_NS}{edcs_id}/edcs/{scrape_date}>'
    insc_uri  = _insc(edcs_id)

    lines = [f'{graph_uri} {{', '']
    lines.append(f'  {insc_uri}')
    lines.append(f'    a epig:Inscription ;')
    lines.append(f'    epig:edcsId {_lit(edcs_id)} ;')

    if orig.get('inscription'):
        lines.append(f'    epig:inscriptionText {_lit(orig["inscription"])} ;')

    if orig.get('province'):
        prov_uri = f'<{PROVINCE_NS}{_safe_id(orig["province"])}>'
        lines.append(f'    epig:province {prov_uri} ;')

    if orig.get('place'):
        place_uri = f'<{PLACE_NS}{_safe_id(orig["place"])}>'
        lines.append(f'    epig:findspot {place_uri} ;')

    if orig.get('dating_from'):
        try:
            lines.append(f'    epig:datingFrom {_int_lit(orig["dating_from"])} ;')
        except (ValueError, TypeError):
            pass

    if orig.get('dating_to'):
        try:
            lines.append(f'    epig:datingTo {_int_lit(orig["dating_to"])} ;')
        except (ValueError, TypeError):
            pass

    if orig.get('publication'):
        lines.append(f'    epig:publication {_lit(orig["publication"])} ;')

    # ExternalDatabaseLink references
    edcs_extdb_uri = f'<{EXTDB_NS}{_safe_id(edcs_id)}>'
    lines.append(f'    epig:externalLink {edcs_extdb_uri} ;')
    sirar_info = SIRAR_MAP.get(edcs_id)
    if sirar_info:
        sirar_extdb_uri = f'<{EXTDB_NS}SIRAR-{sirar_info["sirar_id"]}>'
        lines.append(f'    epig:externalLink {sirar_extdb_uri} ;')

    # schema:url (partner_link)
    partner_url = orig.get('partner_link', '')
    if partner_url:
        lines.append(f'    schema:url <{partner_url}> ;')

    # hmkp:mentions: Source → latest version of each Statement + all CommunityRefs
    for uri in career_latest:
        lines.append(f'    hmkp:mentions {uri} ;')
    for uri in benefaction_latest:
        lines.append(f'    hmkp:mentions {uri} ;')
    for uri in relationship_latest:
        lines.append(f'    hmkp:mentions {uri} ;')
    for uri in community_uris:
        lines.append(f'    hmkp:mentions {uri} ;')

    _close(lines)
    lines.append('')

    # ExternalDatabaseLink resource nodes
    edcs_num = edcs_id.replace('EDCS-', '')
    edcs_clean_url = f'https://edcs.hist.uzh.ch/inscription/{edcs_num}'
    lines.append(f'  {edcs_extdb_uri}')
    lines.append(f'    a epig:ExternalDatabaseLink ;')
    lines.append(f'    epig:database "EDCS" ;')
    lines.append(f'    epig:externalId {_lit(edcs_id)} ;')
    lines.append(f'    schema:url <{edcs_clean_url}> .')
    if sirar_info:
        sirar_extdb_uri = f'<{EXTDB_NS}SIRAR-{sirar_info["sirar_id"]}>'
        lines.append(f'  {sirar_extdb_uri}')
        lines.append(f'    a epig:ExternalDatabaseLink ;')
        lines.append(f'    epig:database "SIRAR" ;')
        lines.append(f'    epig:externalId {_lit(sirar_info["sirar_id"])} ;')
        lines.append(f'    schema:url <{sirar_info["sirar_url"]}> .')

    if orig.get('province'):
        prov_name = orig['province']
        prov_uri  = f'<{PROVINCE_NS}{_safe_id(prov_name)}>'
        lines.append(f'  {prov_uri} a epig:Province ; rdfs:label {_lit(prov_name)} .')

    if orig.get('place'):
        place_name = orig['place']
        place_uri  = f'<{PLACE_NS}{_safe_id(place_name)}>'
        pleiades = PLEIADES_MAP.get(place_name, {})
        pleiades_id = pleiades.get('pleiades_id', '')
        if pleiades_id:
            lines.append(f'  {place_uri} a epig:Place ;')
            lines.append(f'    rdfs:label {_lit(place_name)} ;')
            lines.append(f'    epig:pleiadesId {_lit(pleiades_id)} ;')
            lines.append(f'    owl:sameAs pleiad:{pleiades_id} .')
        else:
            lines.append(f'  {place_uri} a epig:Place ; rdfs:label {_lit(place_name)} .')

    lines += ['', '}', '']
    return lines


# ── EntityReference + Statement graph (史料内在知識層) ────────────────────────

def _build_entity_refs(record: dict) -> list[str]:
    """Emit hmki:EntityReference nodes for all persons and communities."""
    edcs_id = record.get('edcs_id', 'Unknown')
    lines: list[str] = []
    entity_nodes: list[str] = []   # hmke:Entity blocks, deduplicated
    emitted_entities: set[str] = set()
    # epig:SocialStatusStatement blocks, emitted after the person references
    # so each person's own block stays contiguous.
    status_nodes: list[str] = []

    for person in record.get('persons', []):
        p_name = person.get('person_name', '')
        if p_name in ('Parse Error', 'Error', 'No Text'):
            continue
        p_id   = person.get('person_id', 0)
        p_uri  = _eref_person(edcs_id, p_id)

        surface = (person.get('person_name_readable')
                   or person.get('person_name', ''))
        lines.append(f'  {p_uri}')
        lines.append(f'    a epig:PersonReference ;')
        if surface:
            lines.append(f'    hmki:surfaceForm {_lit(surface)} ;')

        if p_name:
            lines.append(f'    epig:personName {_lit(p_name)} ;')
        if person.get('praenomen'):
            lines.append(f'    epig:praenomen {_lit(person["praenomen"])} ;')
        if person.get('nomen'):
            lines.append(f'    epig:nomen {_lit(person["nomen"])} ;')
        if person.get('cognomen'):
            lines.append(f'    epig:cognomen {_lit(person["cognomen"])} ;')
        if person.get('person_name_normalized'):
            lines.append(f'    hmki:normalizedForm {_lit(person["person_name_normalized"])} ;')
        gender = person.get('gender', '')
        if gender and gender != 'unknown':
            lines.append(f'    epig:gender {_lit(gender)} ;')
        if person.get('gender_evidence'):
            lines.append(f'    epig:genderEvidence {_lit(person["gender_evidence"])} ;')
        if person.get('ethnicity'):
            lines.append(f'    epig:ethnicity {_lit(person["ethnicity"])} ;')
        if person.get('ethnicity_evidence'):
            lines.append(f'    epig:ethnicityEvidence {_lit(person["ethnicity_evidence"])} ;')
        if person.get('social_status'):
            lines.append(f'    epig:socialStatus {_lit(person["social_status"])} ;')
        if person.get('social_status_evidence'):
            lines.append(f'    epig:socialStatusEvidence {_lit(person["social_status_evidence"])} ;')
        # Social status statements (classify_social_status.py).  A person can
        # hold several statuses at once — legal standing, ordo, occupation and
        # religious standing are independent axes — so each is a separate node
        # carrying its own evidence and certainty.  epig:socialStatus above is
        # the uncontrolled extraction value and is kept for provenance.
        for n, st in enumerate(person.get('social_statuses') or []):
            st_uri = f'<{ENTITYREF_NS}{_safe_id(edcs_id)}/person/{p_id}/status/{n}>'
            lines.append(f'    epig:hasSocialStatusStatement {st_uri} ;')
            status_nodes.append(f'  {st_uri}')
            status_nodes.append(f'    a epig:SocialStatusStatement ;')
            status_nodes.append(
                f'    epig:socialStatusCategory <{EPIGS_NS}{st["category"]}> ;')
            if st.get('subtype'):
                status_nodes.append(
                    f'    epig:socialStatusSubtype <{EPIGS_NS}{st["subtype"]}> ;')
            if st.get('rank'):
                status_nodes.append(f'    epig:statusRank {_lit(st["rank"])} ;')
            if st.get('evidence'):
                status_nodes.append(f'    epig:statusEvidence {_lit(st["evidence"])} ;')
            if st.get('certainty'):
                status_nodes.append(f'    epig:statusCertainty {_lit(st["certainty"])} ;')
            if st.get('reasoning'):
                status_nodes.append(f'    epig:statusReasoning {_lit(st["reasoning"])} ;')
            if st.get('source'):
                status_nodes.append(
                    f'    epig:socialStatusSource {_lit(st["source"])} ;')
            status_nodes[-1] = status_nodes[-1][:-1].rstrip() + ' .'
            status_nodes.append('')
        wikidata_qid = person.get('person_name_link', '').strip()
        if wikidata_qid and person.get('social_status') == 'emperor':
            norm = person.get('person_name_normalized', '').strip().replace(' ', '_')
            if norm:
                entity_uri = f'<{ENTITY_NS}{norm}>'
                lines.append(f'    hmki:referencesEntity {entity_uri} ;')
                if entity_uri not in emitted_entities:
                    emitted_entities.add(entity_uri)
                    entity_nodes.append(f'  {entity_uri}')
                    entity_nodes.append(f'    a hmke:Entity ;')
                    entity_nodes.append(f'    owl:sameAs <https://www.wikidata.org/entity/{wikidata_qid}> .')
                    entity_nodes.append('')
        age = person.get('age_at_death')
        if age is not None and age != '':
            try:
                lines.append(f'    epig:ageAtDeath {_int_lit(int(age))} ;')
            except (ValueError, TypeError):
                pass
        if person.get('age_at_death_evidence'):
            lines.append(f'    epig:ageAtDeathEvidence {_lit(person["age_at_death_evidence"])} ;')
        divinity = person.get('divinity')
        if divinity is not None:
            lines.append(f'    epig:isDivinity "{str(divinity).lower()}"^^xsd:boolean ;')
        if person.get('divinity_type'):
            lines.append(f'    epig:divinityType {_lit(person["divinity_type"])} ;')
        if person.get('divinity_classification_reasoning'):
            lines.append(f'    epig:divinityClassificationReasoning {_lit(person["divinity_classification_reasoning"])} ;')
        for ev in person.get('life_events', []):
            ev_type = ev.get('event_type', '')
            place = ev.get('place', '')
            place_norm = ev.get('place_normalized') or ''
            place_ev = ev.get('place_evidence', '')
            if ev_type == 'birth':
                if place:
                    lines.append(f'    epig:birthPlace {_lit(place)} ;')
                if place_norm:
                    lines.append(f'    epig:birthPlaceNormalized {_lit(place_norm)} ;')
                if place_ev:
                    lines.append(f'    epig:birthPlaceEvidence {_lit(place_ev)} ;')
            elif ev_type == 'death':
                if place:
                    lines.append(f'    epig:deathPlace {_lit(place)} ;')
                if place_norm:
                    lines.append(f'    epig:deathPlaceNormalized {_lit(place_norm)} ;')
                ps = ev.get('place_source', '')
                if ps:
                    lines.append(f'    epig:deathPlaceSource {_lit(ps)} ;')
                if place_ev:
                    lines.append(f'    epig:deathPlaceEvidence {_lit(place_ev)} ;')

        _close(lines)
        lines.append('')

    lines.extend(entity_nodes)
    lines.extend(status_nodes)

    for community in record.get('communities', []):
        c_name = community.get('community_name', '')
        if not c_name:
            continue
        c_id  = community.get('community_id', 0)
        c_uri = _eref_community(edcs_id, c_id)

        lines.append(f'  {c_uri}')
        lines.append(f'    a epig:CommunityReference ;')
        lines.append(f'    hmki:surfaceForm {_lit(c_name)} ;')
        if community.get('community_name_normalized'):
            lines.append(f'    hmki:normalizedForm {_lit(community["community_name_normalized"])} ;')
        if community.get('community_type'):
            lines.append(f'    epig:communityType {_lit(community["community_type"])} ;')
        if community.get('evidence'):
            lines.append(f'    epig:evidence {_lit(community["evidence"])} ;')

        _close(lines)
        lines.append('')

    return lines


def _career_update_act_uri(activities: list) -> str | None:
    """Return the URI of the activity that added career location fields."""
    act = _act_uri_for_field(activities, 'career_path[].location')
    if act is None:
        act = _act_uri_for_type(activities, 'enrich_career_location')
    return act


def _build_career_statements(record: dict, extract_act_uri: str | None,
                              activities: list) -> tuple[list[str], list[str]]:
    """
    Emit versioned epig:CareerStatement nodes.

    v0: extract-only fields.
    v1: adds location fields (enrich_career_location), linked via prov:wasRevisionOf → v0.
    Returns (lines, latest_uris) where latest_uris[i] is the most recent version URI
    for statement slot i — used by build_source_graph for hmkp:mentions.
    """
    edcs_id = record.get('edcs_id', 'Unknown')
    lines: list[str] = []
    latest_uris: list[str] = []
    i = 0

    location_act_uri = _career_update_act_uri(activities)

    for person in record.get('persons', []):
        if person.get('person_name', '') in ('Parse Error', 'Error', 'No Text'):
            continue
        if not person.get('has_career'):
            continue

        p_id  = person.get('person_id', 0)
        p_uri = _eref_person(edcs_id, p_id)

        career_path = person.get('career_path', [])
        if career_path and isinstance(career_path[0], dict):
            career_sorted = sorted(career_path, key=lambda x: x.get('order', 0))
        else:
            career_sorted = [{'position': p, 'order': idx}
                             for idx, p in enumerate(career_path)]

        for cp in career_sorted:
            has_location = cp.get('location') is not None

            # ── v0: extract-generated fields ──────────────────────────────────
            v0_uri = _mk_career(edcs_id, i, 0)
            lines.append(f'  {v0_uri}')
            lines.append(f'    a epig:CareerStatement ;')
            lines.append(f'    hmki:references {p_uri} ;')
            lines.append(f'    epig:subject {p_uri} ;')
            if cp.get('position'):
                lines.append(f'    epig:positionText {_lit(cp["position"])} ;')
            if cp.get('position_normalized'):
                lines.append(f'    epig:positionNormalized {_lit(cp["position_normalized"])} ;')
            if cp.get('position_abstract'):
                lines.append(f'    epig:positionAbstract {_lit(cp["position_abstract"])} ;')
            if cp.get('position_type'):
                lines.append(f'    epig:positionType {_position_type_uri(cp["position_type"])} ;')
            # 官職の統制語彙（classify_position.py）。全659種のうち主要な
            # 52種のみを定義しているため、対応がない役職には付与しない。
            if cp.get('position_canonical'):
                lines.append(f'    epig:positionCanonical <{EPIGP_NS}{cp["position_canonical"]}> ;')
            if cp.get('position_tier'):
                lines.append(f'    epig:positionTier <{EPIGP_NS}tier_{cp["position_tier"]}> ;')
            if cp.get('position_canonical_source'):
                lines.append(f'    epig:positionCanonicalSource {_lit(cp["position_canonical_source"])} ;')
            if cp.get('victory_title'):
                lines.append(f'    epig:victoryTitle {_lit(cp["victory_title"])} ;')
            if cp.get('position_description'):
                lines.append(f'    epig:positionDescription {_lit(cp["position_description"])} ;')
            order = cp.get('order')
            if order is not None:
                lines.append(f'    epig:order {_int_lit(order)} ;')
            if extract_act_uri:
                lines.append(f'    hmkia:generatedBy {extract_act_uri} ;')
            _close(lines)
            lines.append('')

            latest = v0_uri

            # ── v1: adds location fields (only if enrich was applied) ─────────
            if has_location and location_act_uri:
                v1_uri = _mk_career(edcs_id, i, 1)
                lines.append(f'  {v1_uri}')
                lines.append(f'    a epig:CareerStatement ;')
                lines.append(f'    hmki:references {p_uri} ;')
                lines.append(f'    epig:subject {p_uri} ;')
                if cp.get('position'):
                    lines.append(f'    epig:positionText {_lit(cp["position"])} ;')
                if cp.get('position_normalized'):
                    lines.append(f'    epig:positionNormalized {_lit(cp["position_normalized"])} ;')
                if cp.get('position_abstract'):
                    lines.append(f'    epig:positionAbstract {_lit(cp["position_abstract"])} ;')
                if cp.get('position_type'):
                    lines.append(f'    epig:positionType {_position_type_uri(cp["position_type"])} ;')
                if cp.get('position_canonical'):
                    lines.append(f'    epig:positionCanonical <{EPIGP_NS}{cp["position_canonical"]}> ;')
                if cp.get('position_tier'):
                    lines.append(f'    epig:positionTier <{EPIGP_NS}tier_{cp["position_tier"]}> ;')
                if cp.get('position_canonical_source'):
                    lines.append(f'    epig:positionCanonicalSource {_lit(cp["position_canonical_source"])} ;')
                if cp.get('victory_title'):
                    lines.append(f'    epig:victoryTitle {_lit(cp["victory_title"])} ;')
                if cp.get('position_description'):
                    lines.append(f'    epig:positionDescription {_lit(cp["position_description"])} ;')
                if order is not None:
                    lines.append(f'    epig:order {_int_lit(order)} ;')
                lines.append(f'    epig:location {_lit(cp["location"])} ;')
                if cp.get('location_normalized'):
                    lines.append(f'    epig:locationNormalized {_lit(cp["location_normalized"])} ;')
                if cp.get('location_evidence'):
                    lines.append(f'    epig:locationEvidence {_lit(cp["location_evidence"])} ;')
                lines.append(f'    hmkia:generatedBy {location_act_uri} ;')
                lines.append(f'    prov:wasRevisionOf {v0_uri} ;')
                _close(lines)
                lines.append('')
                latest = v1_uri

            latest_uris.append(latest)
            i += 1

    return lines, latest_uris


# ── FundingType helpers ───────────────────────────────────────────────────────

# Ordered by specificity: more specific patterns first.
_FUNDING_PATTERNS: list[tuple[str, str]] = [
    # Latin expressions
    (r'\bex\s+usuris?\b|\bex\s+reditu\b|\bex\s+reditibus\b', 'interest'),
    (r'\btestamento\b|\bex\s+testamento\b', 'bequest'),
    (r'\bex\s+summa\s+honoraria\b|\bob\s+honorem\b|\bob\s+honor(is|em)\b', 'honorarium'),
    (r'\bpecunia\s+publica\b|\bde\s+publico\b', 'public'),
    (r'\bsua\s+pecunia\b|\bex\s+sua\b|\bde\s+sua\s+pecunia\b|\bimpensa\s+sua\b'
     r'|\bsua\s+impensa\b|\bex\s+sua\s+liberalitate\b|\bsuis\s+sumptibus\b', 'private'),
    (r'\bex\s+mult[ia]\b', 'fine'),
    # English paraphrase in notes field (LLM output) — match only when
    # the phrase indicates the SOURCE of funding, not an intended outcome.
    (r'\bfunded\s+(annually\s+)?from\s+(the\s+)?interest\b'
     r'|\bfrom\s+(the\s+)?interest\b|\bex\s+usuris\b', 'interest'),
    (r'\bbequest\b|\bby\s+will\b|\bby\s+testament\b', 'bequest'),
    (r'\bhonorarium\b|\bsumma\s+honoraria\b', 'honorarium'),
    (r'\bpublic\s+fund', 'public'),
    (r'\bown\s+(money|funds|expense)\b|\bprivate\s+fund', 'private'),
]


def _benef_evidence_text(benef: dict) -> str:
    return ' '.join(filter(None, [
        benef.get('cost', '') or '',
        benef.get('notes', '') or '',
        benef.get('benefaction_text', '') or '',
    ])).lower()


def _infer_funding_types(benef: dict) -> list[str]:
    """
    Return a deduplicated list of epigf: local names inferred from cost/notes fields.

    Returns an empty list when nothing matches: absence of evidence is recorded as
    absence, not as an explicit epigf:unknown assertion.
    """
    import re as _re
    text = _benef_evidence_text(benef)
    seen: set[str] = set()
    found = []
    for pattern, key in _FUNDING_PATTERNS:
        if key not in seen and _re.search(pattern, text, _re.IGNORECASE):
            seen.add(key)
            found.append(key)
    return found


def _infer_recurrence(benef: dict) -> str | None:
    """
    Infer 'annual' / 'perpetual' from attested formulae, else None.

    Inscriptions are elliptic: a benefaction with no recurrence formula is not
    thereby a one-off, so an unattested case yields None and the property is
    omitted rather than asserted as 'once'.
    """
    text = _benef_evidence_text(benef)
    if any(k in text for k in ('quoque anno', 'quotannis', 'singulis annis')):
        return 'annual'
    if 'in perpetuum' in text or 'perpetuo' in text or 'perpetual' in text:
        return 'perpetual'
    return None


def _build_benefaction_statements(record: dict, extract_act_uri: str | None,
                                  activities: list) -> tuple[list[str], int]:
    """
    Emit versioned epig:BenefactionStatement nodes.

    v0: extract-only fields (structural + cost original text).
    v1: adds cost_numeric/unit (enrich_cost), if present.
    v2: adds object split fields (enrich_benef_objects), if present.
    v3: adds recipient fields (enrich_benef_recipients), if present.
    Each version links to previous via prov:wasRevisionOf.
    Returns (lines, latest_uris) where latest_uris[i] is the most recent version URI
    for statement slot i — used by build_source_graph for hmkp:mentions.
    """
    edcs_id = record.get('edcs_id', 'Unknown')
    lines: list[str] = []
    # Per-object nodes for benefactions naming objects in more than one
    # category; collected separately and appended after the statements so the
    # statement block stays contiguous.
    obj_lines: list[str] = []
    latest_uris: list[str] = []
    i = 0

    cost_act_uri  = _act_uri_for_field(activities, 'benefactions[].cost_numeric') \
                    or _act_uri_for_type(activities, 'enrich_cost')
    obj_act_uri   = _act_uri_for_field(activities, 'benefactions[].objects') \
                    or _act_uri_for_type(activities, 'enrich_benef_objects')
    recip_act_uri = _act_uri_for_field(activities, 'benefactions[].recipient_communities') \
                    or _act_uri_for_type(activities, 'enrich_benef_recipients')

    def _emit_benef_base(benef: dict, mk_uri: str,
                         agent_uri: 'str | list | None',
                         agent_is_community: bool,
                         recip_p_ids: list, recip_c_ids: list) -> None:
        lines.append(f'  {mk_uri}')
        lines.append(f'    a epig:BenefactionStatement ;')
        agent_uris_inner = agent_uri if isinstance(agent_uri, list) else ([agent_uri] if agent_uri else [])
        for a_uri in agent_uris_inner:
            lines.append(f'    hmki:references {a_uri} ;')
            lines.append(f'    epig:agent {a_uri} ;')
        for rp_id in recip_p_ids:
            r_uri = _eref_person(edcs_id, rp_id)
            lines.append(f'    hmki:references {r_uri} ;')
            lines.append(f'    epig:recipient {r_uri} ;')
        for rc_id in recip_c_ids:
            r_uri = _eref_community(edcs_id, rc_id)
            lines.append(f'    hmki:references {r_uri} ;')
            lines.append(f'    epig:recipient {r_uri} ;')
        if benef.get('benefaction_type'):
            lines.append(f'    epig:benefactionType {_lit(benef["benefaction_type"])} ;')
        if benef.get('benefaction_text'):
            lines.append(f'    epig:benefactionText {_lit(benef["benefaction_text"])} ;')
        if benef.get('object'):
            lines.append(f'    epig:objectText {_lit(benef["object"])} ;')
        if benef.get('object_type'):
            lines.append(f'    epig:objectType {_lit(benef["object_type"])} ;')
        # Object categories (classify_object_category.py).  The controlled
        # vocabulary lives on benefactions[].objects[], not on the scalar
        # object_type above: objects[] is the post-enrichment split and is what
        # the classifier actually ran over.
        #
        # Only emit the category onto the statement itself when the benefaction
        # names a single object.  501 benefactions list several objects and 135
        # of those span more than one category; flattening them here would pair
        # every category with every subtype and silently corrupt the data.  Such
        # benefactions get their categories on per-object nodes instead, so that
        # each category keeps its own subtype and source.
        objs = benef.get('objects') or []
        classified = [o for o in objs if o.get('object_category')]
        if len(classified) == 1:
            obj = classified[0]
            lines.append(f'    epig:objectCategory <{EPIGO_NS}{obj["object_category"]}> ;')
            if obj.get('object_subtype'):
                lines.append(f'    epig:objectSubtype <{EPIGO_NS}{obj["object_subtype"]}> ;')
            if obj.get('object_category_source'):
                lines.append(f'    epig:objectCategorySource {_lit(obj["object_category_source"])} ;')
        elif len(classified) > 1:
            for n, obj in enumerate(classified):
                o_uri = f'{mk_uri[:-1]}/object/{n}>'
                lines.append(f'    epig:hasObjectStatement {o_uri} ;')
                obj_lines.append(f'  {o_uri}')
                obj_lines.append(f'    a epig:BenefactionObjectStatement ;')
                if obj.get('object'):
                    obj_lines.append(f'    epig:objectText {_lit(obj["object"])} ;')
                if obj.get('object_type'):
                    obj_lines.append(f'    epig:objectType {_lit(obj["object_type"])} ;')
                obj_lines.append(
                    f'    epig:objectCategory <{EPIGO_NS}{obj["object_category"]}> ;')
                if obj.get('object_subtype'):
                    obj_lines.append(
                        f'    epig:objectSubtype <{EPIGO_NS}{obj["object_subtype"]}> ;')
                if obj.get('object_category_source'):
                    obj_lines.append(
                        f'    epig:objectCategorySource '
                        f'{_lit(obj["object_category_source"])} ;')
                obj_lines[-1] = obj_lines[-1][:-1].rstrip() + ' .'
                obj_lines.append('')
        if benef.get('cost'):
            lines.append(f'    epig:costOriginalText {_lit(benef["cost"])} ;')
        if benef.get('cost_conversion_reasoning'):
            lines.append(f'    epig:costConversionReasoning {_lit(benef["cost_conversion_reasoning"])} ;')

        # Funding provenance (ex sua pecunia / ex testamento / pecunia publica …).
        # Only emitted when the inscription text actually supports it: an
        # unmatched benefaction gets no fundingType rather than epigf:unknown,
        # and recurrence is omitted unless a formula attests it.
        funding_keys = _infer_funding_types(benef)
        for key in funding_keys:
            lines.append(f'    epig:fundingType <{EPIGF_NS}{key}> ;')
        # Evidence is only evidence of something: without a matched fundingType the
        # cost/notes text is a description of the gift, not of where the money came
        # from, so it would misrepresent the ontology's intent to record it here.
        if funding_keys:
            funding_evidence = ' | '.join(
                p for p in (benef.get('cost', ''), benef.get('notes', '')) if p
            )
            if funding_evidence:
                lines.append(f'    epig:fundingEvidence {_lit(funding_evidence)} ;')
        recurrence = _infer_recurrence(benef)
        if recurrence:
            lines.append(f'    epig:recurrence {_lit(recurrence)} ;')

    # Always use persons[].benefactions as primary source — it contains enriched
    # fields (cost_numeric, objects, recipient_communities) that top-level lacks.
    # When no person-level benefactions exist, fall back to top-level benefactions.
    #
    # Deduplication: when the same physical act (same object + benefaction_type)
    # appears under multiple persons, merge into one BenefactionStatement with
    # all agents listed.  We use (benefaction_type, object, benefaction_text[:60])
    # as the identity key; the first occurrence wins as the canonical benef dict.
    raw_person_benefactions = []
    for person in record.get('persons', []):
        if person.get('person_name', '') in ('Parse Error', 'Error', 'No Text'):
            continue
        p_id  = person.get('person_id', 0)
        p_uri = _eref_person(edcs_id, p_id)
        for benef in person.get('benefactions', []):
            raw_person_benefactions.append((benef, p_uri))

    # Group by identity key → (canonical_benef, [agent_uris])
    # Key: (benefaction_type, object) — benefaction_text often varies per agent,
    # so we exclude it from the key to catch cross-agent duplicates of the same act.
    from collections import OrderedDict
    merged: 'OrderedDict[tuple, tuple]' = OrderedDict()
    for benef, p_uri in raw_person_benefactions:
        key = (
            benef.get('benefaction_type', ''),
            benef.get('object', ''),
        )
        if key not in merged:
            merged[key] = (benef, [])
        if p_uri not in merged[key][1]:
            merged[key][1].append(p_uri)

    person_benefactions = [(benef, agents) for benef, agents in merged.values()]

    top_benefactions = record.get('benefactions', [])
    use_top = not person_benefactions and bool(top_benefactions)

    if person_benefactions:
        for benef, agent_uris in person_benefactions:
            has_cost  = benef.get('cost_numeric') is not None and cost_act_uri
            has_obj   = benef.get('objects') is not None and obj_act_uri
            has_recip = benef.get('recipient_communities') is not None and recip_act_uri

            # ── v0: extract-only ──────────────────────────────────────────────────
            v0_uri = _mk_benefaction(edcs_id, i, 0)
            _emit_benef_base(benef, v0_uri, agent_uris, False, [], [])
            if extract_act_uri:
                lines.append(f'    hmkia:generatedBy {extract_act_uri} ;')
            _close(lines)
            lines.append('')

            prev_uri = v0_uri
            v = 1

            # ── v1: cost fields ───────────────────────────────────────────────────
            if has_cost:
                vn_uri = _mk_benefaction(edcs_id, i, v)
                _emit_benef_base(benef, vn_uri, agent_uris, False, [], [])
                try:
                    lines.append(f'    epig:costNumeric {_int_lit(benef["cost_numeric"])} ;')
                except (ValueError, TypeError):
                    lines.append(f'    epig:costNumeric {_lit(str(benef["cost_numeric"]))} ;')
                if benef.get('cost_unit'):
                    lines.append(f'    epig:costUnit {_lit(benef["cost_unit"])} ;')
                lines.append(f'    hmkia:generatedBy {cost_act_uri} ;')
                lines.append(f'    prov:wasRevisionOf {prev_uri} ;')
                _close(lines)
                lines.append('')
                prev_uri = vn_uri
                v += 1

            # ── v2: object split fields ───────────────────────────────────────────
            if has_obj:
                vn_uri = _mk_benefaction(edcs_id, i, v)
                _emit_benef_base(benef, vn_uri, agent_uris, False, [], [])
                if has_cost and benef.get('cost_numeric') is not None:
                    try:
                        lines.append(f'    epig:costNumeric {_int_lit(benef["cost_numeric"])} ;')
                    except (ValueError, TypeError):
                        lines.append(f'    epig:costNumeric {_lit(str(benef["cost_numeric"]))} ;')
                    if benef.get('cost_unit'):
                        lines.append(f'    epig:costUnit {_lit(benef["cost_unit"])} ;')
                lines.append(f'    hmkia:generatedBy {obj_act_uri} ;')
                lines.append(f'    prov:wasRevisionOf {prev_uri} ;')
                _close(lines)
                lines.append('')
                prev_uri = vn_uri
                v += 1

            # ── v3: recipient fields ──────────────────────────────────────────────
            if has_recip:
                # recipient_communities は enrich が付与した受益者。community_id が
                # null のもの（碑文中の共同体一覧に対応先がないもの）は URI を作れ
                # ないため除く。受益者は v3 以降でのみ現れる値なので、v0〜v2 には
                # 渡さずこのバージョンから出力する。
                recip_c_ids = [
                    rc.get('community_id')
                    for rc in (benef.get('recipient_communities') or [])
                    if rc.get('community_id') is not None
                ]
                vn_uri = _mk_benefaction(edcs_id, i, v)
                _emit_benef_base(benef, vn_uri, agent_uris, False, [], recip_c_ids)
                if has_cost and benef.get('cost_numeric') is not None:
                    try:
                        lines.append(f'    epig:costNumeric {_int_lit(benef["cost_numeric"])} ;')
                    except (ValueError, TypeError):
                        lines.append(f'    epig:costNumeric {_lit(str(benef["cost_numeric"]))} ;')
                    if benef.get('cost_unit'):
                        lines.append(f'    epig:costUnit {_lit(benef["cost_unit"])} ;')
                lines.append(f'    hmkia:generatedBy {recip_act_uri} ;')
                lines.append(f'    prov:wasRevisionOf {prev_uri} ;')
                _close(lines)
                lines.append('')
                prev_uri = vn_uri

            latest_uris.append(prev_uri)
            i += 1

    if use_top:
        for benef in top_benefactions:
            agent_p_id  = benef.get('agent_person_id')
            agent_c_id  = benef.get('agent_community_id')
            recip_p_ids = benef.get('recipient_person_ids', [])
            recip_c_ids = benef.get('recipient_community_ids', [])
            if agent_p_id is not None:
                agent_uri = _eref_person(edcs_id, agent_p_id)
            elif agent_c_id is not None:
                agent_uri = _eref_community(edcs_id, agent_c_id)
            else:
                agent_uri = None
            v0_uri = _mk_benefaction(edcs_id, i, 0)
            _emit_benef_base(benef, v0_uri, agent_uri, agent_c_id is not None,
                             recip_p_ids, recip_c_ids)
            if extract_act_uri:
                lines.append(f'    hmkia:generatedBy {extract_act_uri} ;')
            _close(lines)
            lines.append('')
            latest_uris.append(v0_uri)
            i += 1

    return lines + obj_lines, latest_uris


def _build_relationship_statements(record: dict) -> tuple[list[str], list[str]]:
    """
    Emit versioned epig:RelationshipStatement nodes from person_relationships.

    When a reextract activity exists:
      v0: the original extract values, sourced from _provenance.snapshots if available
          (so the snapshot's actual property values are preserved, not the current ones)
      v1: current (reextracted) values, linked via prov:wasRevisionOf → v0

    When no reextract: single v0 with current values.

    Returns (lines, latest_uris) where latest_uris[i] is the most recent version URI
    for statement slot i — used by build_source_graph for hmkp:mentions.
    """
    edcs_id = record.get('edcs_id', 'Unknown')
    lines: list[str] = []
    latest_uris: list[str] = []
    provenance = record.get('_provenance', {})
    activities = provenance.get('activities', [])

    extract_rel_uri   = _act_uri_for_type(activities, 'extract')
    # _act_uri_for_field looks for the activity that lists 'person_relationships'
    # in generated_fields — that is always the reextract act when present.
    # Fall back to type-based lookup. Note: reextract_rel_uri must differ from
    # extract_rel_uri to trigger v0/v1 versioning; we compare activity IDs below.
    _reextract_act = next(
        (a for a in activities if a.get('type') == 'reextract_relationships'), None
    ) or next(
        (a for a in activities
         if 'person_relationships' in a.get('generated_fields', [])
         and a.get('type') != 'extract'), None
    )
    reextract_rel_uri = _activity_uri(_reextract_act['activity_id']) if _reextract_act else None
    extract_rel_act_id = next(
        (a['activity_id'] for a in activities if a.get('type') == 'extract'), None
    )
    has_reextract = bool(reextract_rel_uri and (
        not _reextract_act or _reextract_act.get('activity_id') != extract_rel_act_id
    ))

    # Build index of snapshot values keyed by (source_person_id, target_person_id, target_community_id)
    # so we can look up the original extract values for each relationship slot.
    snapshot_rels: dict[tuple, dict] = {}
    for snap in provenance.get('snapshots', []):
        if snap.get('field') != 'person_relationships':
            continue
        for snap_rel in snap.get('value', []):
            key = (
                snap_rel.get('source_person_id'),
                snap_rel.get('target_person_id'),
                snap_rel.get('target_community_id'),
            )
            snapshot_rels[key] = snap_rel

    rels = record.get('person_relationships', record.get('relationships', []))
    i = 0

    def _rel_triples(mk_uri: str, rel_dict: dict) -> None:
        src_p_id = rel_dict.get('source_person_id')
        tgt_p_id = rel_dict.get('target_person_id')
        tgt_c_id = rel_dict.get('target_community_id')
        src_uri = _eref_person(edcs_id, src_p_id)
        tgt_uri = (_eref_person(edcs_id, tgt_p_id) if tgt_p_id is not None
                   else _eref_community(edcs_id, tgt_c_id))
        lines.append(f'  {mk_uri}')
        lines.append(f'    a epig:RelationshipStatement ;')
        lines.append(f'    hmki:references {src_uri} ;')
        lines.append(f'    hmki:references {tgt_uri} ;')
        lines.append(f'    epig:source {src_uri} ;')
        lines.append(f'    epig:target {tgt_uri} ;')
        if rel_dict.get('type'):
            lines.append(f'    epig:relationshipType {_lit(rel_dict["type"])} ;')
        if rel_dict.get('property'):
            lines.append(f'    epig:relationshipProperty {_lit(rel_dict["property"])} ;')
        if rel_dict.get('property_text'):
            lines.append(f'    epig:evidence {_lit(rel_dict["property_text"])} ;')

    for rel in rels:
        src_p_id = rel.get('source_person_id')
        tgt_p_id = rel.get('target_person_id')
        tgt_c_id = rel.get('target_community_id')

        if src_p_id is None:
            continue
        if tgt_p_id is None and tgt_c_id is None:
            continue

        if has_reextract:
            # v0: original extract values (from snapshot if available, else current)
            snap_key = (src_p_id, tgt_p_id, tgt_c_id)
            v0_rel = snapshot_rels.get(snap_key, rel)
            v0_uri = _mk_relationship(edcs_id, i, 0)
            _rel_triples(v0_uri, v0_rel)
            if extract_rel_uri:
                lines.append(f'    hmkia:generatedBy {extract_rel_uri} ;')
            _close(lines)
            lines.append('')
            # v1: reextracted (current) values
            v1_uri = _mk_relationship(edcs_id, i, 1)
            _rel_triples(v1_uri, rel)
            lines.append(f'    hmkia:generatedBy {reextract_rel_uri} ;')
            lines.append(f'    prov:wasRevisionOf {v0_uri} ;')
            _close(lines)
            lines.append('')
            latest_uris.append(v1_uri)
        else:
            # no reextract: single v0
            v0_uri = _mk_relationship(edcs_id, i, 0)
            _rel_triples(v0_uri, rel)
            act_uri = extract_rel_uri or reextract_rel_uri
            if act_uri:
                lines.append(f'    hmkia:generatedBy {act_uri} ;')
            _close(lines)
            lines.append('')
            latest_uris.append(v0_uri)

        i += 1

    return lines, latest_uris


# ── History graph (superseded values) ─────────────────────────────────────────

# JSON field -> RDF predicate for the fields that can appear in value_history.
# EntityReference attributes only: statements already carry their own _vN chain,
# so a superseded statement value is reachable without a history entry.
HISTORY_FIELD_PREDICATE = {
    'persons[].person_name':                       'epig:personName',
    'persons[].person_name_readable':              'hmki:surfaceForm',
    'persons[].praenomen':                         'epig:praenomen',
    'persons[].nomen':                             'epig:nomen',
    'persons[].cognomen':                          'epig:cognomen',
    'persons[].person_name_normalized':            'hmki:normalizedForm',
    'persons[].gender':                            'epig:gender',
    'persons[].gender_evidence':                   'epig:genderEvidence',
    'persons[].ethnicity':                         'epig:ethnicity',
    'persons[].ethnicity_evidence':                'epig:ethnicityEvidence',
    'persons[].social_status':                     'epig:socialStatus',
    'persons[].social_status_evidence':            'epig:socialStatusEvidence',
    'persons[].social_statuses':                   'epig:hasSocialStatusStatement',
    'career_path[].position_canonical':            'epig:positionCanonical',
    'career_path[].position_tier':                 'epig:positionTier',
    'career_path[].position_canonical_source':     'epig:positionCanonicalSource',
    'career_path[].victory_title':                 'epig:victoryTitle',
    'persons[].social_status_source':              'epig:socialStatusSource',
    'benefactions[].objects[].object_category':    'epig:objectCategory',
    'benefactions[].objects[].object_subtype':     'epig:objectSubtype',
    'benefactions[].objects[].object_category_source': 'epig:objectCategorySource',
    'persons[].age_at_death':                      'epig:ageAtDeath',
    'persons[].age_at_death_evidence':             'epig:ageAtDeathEvidence',
    'persons[].divinity':                          'epig:isDivinity',
    'persons[].divinity_type':                     'epig:divinityType',
    'persons[].divinity_classification_reasoning': 'epig:divinityClassificationReasoning',
    'communities[].community_name':                'hmki:surfaceForm',
    'communities[].community_name_normalized':     'hmki:normalizedForm',
    'communities[].community_type':                'epig:communityType',
    'communities[].evidence':                      'epig:evidence',
}

HISTORY_PATH_RE = re.compile(r'^(?P<kind>person|community)/(?P<idx>\d+)\.(?P<field>.+)$')


def _history_value_literal(field_label: str, value) -> str | None:
    """Render a superseded value using the same datatype as the live triple."""
    if value is None or value == '' or value == []:
        return None
    if field_label == 'persons[].divinity':
        return f'"{str(value).lower()}"^^xsd:boolean'
    if field_label == 'persons[].age_at_death':
        try:
            return _int_lit(int(value))
        except (TypeError, ValueError):
            return None
    return _lit(value)


def build_history_graph(record: dict) -> list[str]:
    """
    Emit superseded EntityReference values into an append-only history graph.

    EntityReference URIs are stable and their attributes live in a graph named
    after the extract date, so regenerating an inscription rewrites that graph
    in place and the previous value disappears from the store. Statements avoid
    this by minting _vN successors; entity references cannot, because hundreds
    of statements cite them (see the editor write-back rationale).

    Each superseded value therefore becomes its own prov:Entity, tied to the
    reference it is a past state of by prov:specializationOf, and bracketed by
    prov:generatedAtTime / prov:invalidatedAtTime. The graph is separate from
    the current-value graph so ordinary read queries never pay for it, and it
    is keyed on the inscription rather than a run date so re-ingest adds to it
    rather than replacing it.

    All terms are PROV-O, which epig_ontology.ttl already imports; no new
    vocabulary is required.
    """
    history = record.get('_provenance', {}).get('value_history', [])
    if not history:
        return []

    edcs_id = record.get('edcs_id', 'Unknown')
    graph_uri = f'<{GRAPH_NS}{_safe_id(edcs_id)}/history>'
    lines = [f'{graph_uri} {{', '']

    # Number the states of each attribute in the order they were superseded, so
    # the URI carries the sequence and successive states can be chained.
    seen = defaultdict(int)
    emitted = 0

    for entry in sorted(history, key=lambda e: e.get('superseded_at') or ''):
        path = entry.get('path', '')
        m = HISTORY_PATH_RE.match(path)
        field_label = entry.get('field', '')
        predicate = HISTORY_FIELD_PREDICATE.get(field_label)
        if not m or not predicate:
            continue
        value_lit = _history_value_literal(field_label, entry.get('value'))
        if value_lit is None:
            continue

        idx = int(m.group('idx'))
        ref_uri = (_eref_person(edcs_id, idx) if m.group('kind') == 'person'
                   else _eref_community(edcs_id, idx))

        key = f'{m.group("kind")}/{idx}/{m.group("field")}'
        n = seen[key]
        seen[key] = n + 1
        state_uri = (f'<{ENTITYREF_NS}{_safe_id(edcs_id)}/{m.group("kind")}/'
                     f'{idx}/{m.group("field")}/{n}>')

        lines.append(f'  {state_uri}')
        lines.append(f'    a prov:Entity ;')
        lines.append(f'    prov:specializationOf {ref_uri} ;')
        lines.append(f'    {predicate} {value_lit} ;')
        if entry.get('generated_by'):
            lines.append(f'    hmkia:generatedBy {_activity_uri(entry["generated_by"])} ;')
        if entry.get('generated_at'):
            lines.append(f'    prov:generatedAtTime "{entry["generated_at"]}"^^xsd:dateTime ;')
        if entry.get('superseded_by'):
            lines.append(f'    prov:wasInvalidatedBy {_activity_uri(entry["superseded_by"])} ;')
        if n > 0:
            prev = (f'<{ENTITYREF_NS}{_safe_id(edcs_id)}/{m.group("kind")}/'
                    f'{idx}/{m.group("field")}/{n - 1}>')
            lines.append(f'    prov:wasRevisionOf {prev} ;')
        lines.append(f'    prov:invalidatedAtTime '
                     f'"{entry.get("superseded_at", "")}"^^xsd:dateTime .')
        lines.append('')
        emitted += 1

    if not emitted:
        return []

    lines.append('}')
    lines.append('')
    return lines


def build_intrinsic_graph(record: dict, llm_date: str,
                          extract_act_uri: str | None
                          ) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    """Build the Claude/LLM TriG block (EntityReferences + *Statements).

    Returns (lines, career_latest, benefaction_latest, relationship_latest, community_uris)
    so that the caller can pass all URI lists to build_source_graph.
    community_uris contains one entityref URI per community (no versioning).
    """
    edcs_id   = record.get('edcs_id', 'Unknown')
    graph_uri = f'<{GRAPH_NS}{edcs_id}/claude/{llm_date}>'
    activities = record.get('_provenance', {}).get('activities', [])

    lines = [f'{graph_uri} {{', '']

    eref_lines = _build_entity_refs(record)
    if eref_lines:
        lines += ['  # EntityReferences', ''] + eref_lines

    career_lines, career_latest = _build_career_statements(record, extract_act_uri, activities)
    if career_lines:
        lines += ['  # CareerStatements', ''] + career_lines

    benef_lines, benef_latest = _build_benefaction_statements(record, extract_act_uri, activities)
    if benef_lines:
        lines += ['  # BenefactionStatements', ''] + benef_lines

    rel_lines, rel_latest = _build_relationship_statements(record)
    if rel_lines:
        lines += ['  # RelationshipStatements', ''] + rel_lines

    community_uris = [
        _eref_community(edcs_id, c.get('community_id', idx))
        for idx, c in enumerate(record.get('communities', []))
        if c.get('community_name', '')
    ]

    lines += ['}', '']
    return lines, career_latest, benef_latest, rel_latest, community_uris


# ── File-level processing ─────────────────────────────────────────────────────

def process_json_file(json_path: Path, output_path: Path, scrape_date: str,
                      researchers: 'list[dict]' = None) -> int:
    """Convert one career graph JSON file to a HIMIKO-aligned TriG file."""
    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, list):
        data = [data]

    all_activities = _collect_activities(data)
    extract_act_id, llm_date = _extract_act(all_activities)
    if not llm_date:
        llm_date = scrape_date
    extract_act_uri = _activity_uri(extract_act_id) if extract_act_id else None

    parts: list[str] = [PREFIXES, '']

    # ── Provenance graph ──────────────────────────────────────────────────────
    prov_lines = build_provenance_graph(all_activities, researchers=researchers or [])

    entity_link_lines: list[str] = []
    for record in data:
        entity_link_lines += build_entity_links(
            record, llm_date, scrape_date, extract_act_id)

    # Inject entity links before closing brace
    closing = prov_lines[-1]  # should be '}'
    prov_lines = prov_lines[:-1] + entity_link_lines + [closing, '']
    parts.append('\n'.join(prov_lines))

    # ── Per-record graphs ─────────────────────────────────────────────────────
    # Build intrinsic (statements) first so we know the latest-version URIs,
    # then build source so hmkp:mentions points to the latest version.
    for record in data:
        edcs_id = record.get('edcs_id', 'Unknown')
        if edcs_id == 'Unknown':
            continue

        intrinsic_lines, career_latest, benef_latest, rel_latest, community_uris = \
            build_intrinsic_graph(record, llm_date, extract_act_uri)

        source_lines = build_source_graph(
            record, scrape_date, career_latest, benef_latest, rel_latest, community_uris)

        parts.append('\n'.join(source_lines))
        parts.append('\n'.join(intrinsic_lines))

        history_lines = build_history_graph(record)
        if history_lines:
            parts.append('\n'.join(history_lines))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(parts))

    return len(data)


# ── Directory iteration ───────────────────────────────────────────────────────

def iter_place_dirs(model_dir: Path):
    """Iterate place dirs, handling flat and province-layered structures."""
    for entry in sorted(model_dir.iterdir()):
        if not entry.is_dir():
            continue
        if any(entry.glob('*.json')):
            yield entry
        else:
            for sub in sorted(entry.iterdir()):
                if sub.is_dir():
                    yield sub


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description='Generate HIMIKO-aligned TriG RDF from career graph JSON'
    )
    parser.add_argument('--model', '-m', default='claude',
                        help='Model subdirectory (default: claude)')
    parser.add_argument('--places', '-p', default=None,
                        help='Comma-separated place folder names to process (default: all)')
    parser.add_argument('--scrape-date', default='2026-01-15',
                        help='Date of EDCS scrape for graph URI (default: 2026-01-15)')
    parser.add_argument('--merge', action='store_true',
                        help='Also write a merged all.trig file')
    parser.add_argument('--input-dir', default=None,
                        help=f'Override input base dir (default: {INPUT_DIR})')
    parser.add_argument('--output-dir', default=None,
                        help=f'Override output base dir (default: {OUTPUT_DIR})')
    parser.add_argument(
        '--researcher', action='append', dest='researchers', default=[],
        metavar='NAME|URI[|ORCID]',
        help=(
            'Human researcher to record as responsible party. '
            'Format: "Display Name|http://...agent/person/id[|https://orcid.org/...]". '
            'Repeat for multiple researchers.'
        ),
    )
    args = parser.parse_args()

    # Parse --researcher arguments into dicts
    parsed_researchers: list[dict] = []
    for spec in args.researchers:
        parts_r = spec.split('|', 2)
        name  = parts_r[0].strip()
        uri   = parts_r[1].strip() if len(parts_r) > 1 else ''
        orcid = parts_r[2].strip() if len(parts_r) > 2 else ''
        if name and uri:
            parsed_researchers.append({'name': name, 'uri': uri, 'orcid': orcid})

    global PLEIADES_MAP, SIRAR_MAP
    PLEIADES_MAP = _load_pleiades_mapping()
    SIRAR_MAP = _load_sirar_mapping()

    input_base = Path(args.input_dir) if args.input_dir else INPUT_DIR
    output_base = Path(args.output_dir) if args.output_dir else OUTPUT_DIR

    model_dir = input_base / args.model
    if not model_dir.exists():
        print(f'Error: input directory not found: {model_dir}')
        return 1

    place_dirs = list(iter_place_dirs(model_dir))
    if args.places:
        names = {p.strip() for p in args.places.split(',')}
        place_dirs = [d for d in place_dirs if d.name in names]
        if not place_dirs:
            print(f'No matching place dirs found: {args.places}')
            return 1

    print('=' * 70)
    print('HIMIKO-aligned RDF Generation')
    print('=' * 70)
    print(f'Model        : {args.model}')
    print(f'Input        : {model_dir}')
    print(f'Output       : {output_base / args.model}')
    print(f'Scrape date  : {args.scrape_date}')
    print(f'Places       : {len(place_dirs)}')
    print()

    total_files   = 0
    total_records = 0
    merge_parts   = [PREFIXES, ''] if args.merge else None

    for place_dir in place_dirs:
        province   = place_dir.parent.name
        place_name = place_dir.name

        for json_path in sorted(place_dir.glob('*.json')):
            if province == args.model:
                out_path = output_base / args.model / place_name / (place_name + '.trig')
            else:
                out_path = (output_base / args.model / province
                            / place_name / (place_name + '.trig'))

            try:
                n = process_json_file(json_path, out_path, args.scrape_date,
                                      researchers=parsed_researchers)
                print(f'  OK {place_name}  ({n} records) -> {out_path.relative_to(output_base)}')
                total_files   += 1
                total_records += n

                if merge_parts is not None:
                    with open(out_path, encoding='utf-8') as f:
                        content = f.read()
                    body = re.sub(r'^@prefix[^\n]*\n', '', content, flags=re.MULTILINE)
                    merge_parts.append(body)

            except Exception as e:
                print(f'  FAIL {place_name}: {e}')
                import traceback
                traceback.print_exc()

    if args.merge and merge_parts:
        merge_path = output_base / args.model / 'all.trig'
        merge_path.parent.mkdir(parents=True, exist_ok=True)
        with open(merge_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(merge_parts))
        size_mb = merge_path.stat().st_size / (1024 * 1024)
        print(f'\nMerged file: {merge_path}  ({size_mb:.1f} MB)')

    print()
    print('=' * 70)
    print(f'Files written  : {total_files}')
    print(f'Records output : {total_records}')
    print('=' * 70)
    return 0


if __name__ == '__main__':
    sys.exit(main())
