#!/usr/bin/env python3
"""
Apply human editorial corrections (edit-diff JSON) to the Fuseki triplestore.

The browser editor cannot write to Fuseki directly: doing so would require
embedding write credentials in client-side JavaScript on a public server.
Instead it exports a diff describing what a human changed, and this script
applies it with credentials held outside the browser.

Corrections are recorded the same way LLM enrichment already is — as a new
versioned Statement linked to its predecessor by prov:wasRevisionOf, generated
by an hmkia:InterpretationAct whose agent is the human editor. Reification is
deliberately not used: the project moved to version chains, and keeping human
edits in a second mechanism would split the provenance record in two.

Entity references (PersonReference / CommunityReference) are not versioned in
the generated data, so edits to them are applied in place within a new editor
graph that overrides the original value.

Usage:
    python provenance/apply_editor_json.py edit_EDCS-xxx_*.json \
        --endpoint http://host/himiko_epigraphy \
        --user admin --password-env FUSEKI_PASSWORD
    python provenance/apply_editor_json.py edits/*.json --dry-run
"""

import argparse
import getpass
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ── Namespaces ────────────────────────────────────────────────────────────────

BASE       = 'http://epigraphic-careers.org/'
EPIG_NS    = BASE + 'ontology#'
GRAPH_NS   = BASE + 'graph/'
ACTIVITY_NS = BASE + 'activity/'
AGENT_NS   = BASE + 'agent/'
HMKI_NS    = 'urn:himiko:ontology:intrinsic:'
HMKIA_NS   = 'urn:himiko:ontology:interpretation:'
PROV_NS    = 'http://www.w3.org/ns/prov#'
XSD_NS     = 'http://www.w3.org/2001/XMLSchema#'
RDFS_NS    = 'http://www.w3.org/2000/01/rdf-schema#'

PREFIX_MAP = {
    'epig':  EPIG_NS,
    'hmki':  HMKI_NS,
    'hmkia': HMKIA_NS,
    'prov':  PROV_NS,
    'xsd':   XSD_NS,
    'rdfs':  'http://www.w3.org/2000/01/rdf-schema#',
}

# Statements are versioned by minting a successor URI (_vN). Entity references
# deliberately are not: they are hubs cited by hundreds of statements, and a new
# URI per correction would leave every existing citation pointing at the
# superseded version. Their corrections are layered by named graph instead.
VERSIONED_TYPES = {'CareerStatement', 'BenefactionStatement', 'RelationshipStatement'}

VERSION_RE = re.compile(r'^(?P<stem>.*)_v(?P<n>\d+)$')


# ── Serialisation helpers ─────────────────────────────────────────────────────

def _esc(s: str) -> str:
    return (str(s).replace('\\', '\\\\').replace('"', '\\"')
            .replace('\n', '\\n').replace('\r', '\\r'))


def _literal(value, datatype: str) -> str:
    """Render a JSON value as a SPARQL literal of the requested datatype."""
    if datatype == 'xsd:integer':
        return f'"{int(value)}"^^<{XSD_NS}integer>'
    if datatype == 'xsd:boolean':
        truthy = value if isinstance(value, bool) else str(value).lower() == 'true'
        return f'"{"true" if truthy else "false"}"^^<{XSD_NS}boolean>'
    return f'"{_esc(value)}"'


def _expand(curie: str) -> str:
    """Expand a prefixed name (epig:cognomen) to a full IRI."""
    if curie.startswith('http://') or curie.startswith('urn:'):
        return curie
    if ':' not in curie:
        raise ValueError(f'cannot expand predicate: {curie}')
    prefix, local = curie.split(':', 1)
    if prefix not in PREFIX_MAP:
        raise ValueError(f'unknown prefix in predicate: {curie}')
    return PREFIX_MAP[prefix] + local


def _next_version_uri(uri: str) -> str:
    """mk/.../benefaction/0_v3 -> mk/.../benefaction/0_v4 (else append _v1)."""
    m = VERSION_RE.match(uri)
    if m:
        return f"{m.group('stem')}_v{int(m.group('n')) + 1}"
    return uri + '_v1'


# ── SPARQL transport ──────────────────────────────────────────────────────────

class Fuseki:
    def __init__(self, endpoint: str, user: str = None, password: str = None):
        self.query_url = endpoint.rstrip('/') + '/sparql'
        self.update_url = endpoint.rstrip('/') + '/update'
        self._auth = None
        if user:
            import base64
            token = base64.b64encode(f'{user}:{password}'.encode()).decode()
            self._auth = f'Basic {token}'

    def _post(self, url: str, data: bytes, content_type: str, accept: str = None):
        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('Content-Type', content_type)
        if accept:
            req.add_header('Accept', accept)
        if self._auth:
            req.add_header('Authorization', self._auth)
        with urllib.request.urlopen(req, timeout=300) as resp:
            return resp.read().decode('utf-8')

    def select(self, query: str) -> list:
        body = urllib.parse.urlencode({'query': query}).encode()
        raw = self._post(self.query_url, body,
                         'application/x-www-form-urlencoded',
                         'application/sparql-results+json')
        return json.loads(raw)['results']['bindings']

    def update(self, query: str) -> None:
        self._post(self.update_url, query.encode('utf-8'),
                   'application/sparql-update')


# ── Verification ──────────────────────────────────────────────────────────────

def current_value(fuseki: Fuseki, subject: str, predicate_iri: str):
    """
    Return the value in force for subject/predicate, or None.

    A resource may hold the same property in several graphs: once per machine
    extraction run, plus once per human correction. Editor graphs override
    machine output, and among graphs of the same kind the latest timestamp wins
    — graph names sort chronologically, so ordering by graph IRI descending and
    preferring /editor/ yields the value a reader would currently see.
    """
    rows = fuseki.select(f'''
        SELECT ?o ?g WHERE {{ GRAPH ?g {{ <{subject}> <{predicate_iri}> ?o }} }}
        ORDER BY DESC(CONTAINS(STR(?g), "/editor/")) DESC(STR(?g))
        LIMIT 1
    ''')
    if not rows:
        return None
    return rows[0]['o']['value']


def latest_edit_act(fuseki: Fuseki, subject: str, predicate_iri: str):
    """
    Return the InterpretationAct of the most recent human correction to this
    property, or None if it has never been corrected by hand.

    Used to chain successive corrections with hmkia:revises so the editorial
    history forms an ordered sequence rather than a flat pile of graphs.
    """
    rows = fuseki.select(f'''
        SELECT ?act WHERE {{
            GRAPH ?g {{ <{subject}> <{predicate_iri}> ?o ; <{HMKIA_NS}generatedBy> ?act }}
            FILTER(CONTAINS(STR(?g), "/editor/"))
        }}
        ORDER BY DESC(STR(?g))
        LIMIT 1
    ''')
    return rows[0]['act']['value'] if rows else None


def check_conflict(fuseki: Fuseki, edit: dict) -> 'str | None':
    """
    Return a message if the stored value no longer matches old_value.

    Guards against overwriting a change someone else made after the editor
    loaded the data.
    """
    predicate_iri = _expand(edit['predicate'])
    stored = current_value(fuseki, edit['subject'], predicate_iri)
    expected = edit.get('old_value')
    if expected in (None, '') and stored in (None, ''):
        return None
    if str(stored or '') != str(expected or ''):
        return (f"{edit['subject']} {edit['predicate']}: "
                f"expected {expected!r} but store holds {stored!r}")
    return None


# ── Update construction ───────────────────────────────────────────────────────

def build_update(payload: dict, edits: list, timestamp: str,
                 prior_acts: dict = None) -> str:
    """
    Build a single INSERT DATA writing all edits into one editor graph.

    Entity references keep their URI: they are referred to by many statements
    (a single PersonReference is cited by hundreds of epig:agent / epig:source
    triples), so minting a new URI per correction would strand every one of
    those references on the superseded version. The correction is instead
    recorded in a new editor graph, and precedence is resolved by graph: editor
    graphs override machine output, later timestamps override earlier ones.

    Statements are different — they are leaf nodes that little else points at —
    so the pipeline's existing _vN chain is extended for them.

    prior_acts maps "subject predicate" to the InterpretationAct of the previous
    human correction, linked via hmkia:revises to order the editorial history.
    """
    edcs_id = payload['edcs_id']
    editor = payload['editor']
    safe_ts = re.sub(r'[^0-9A-Za-z]', '', timestamp)
    graph_uri = f'{GRAPH_NS}{edcs_id}/editor/{safe_ts}'
    act_uri = f'{ACTIVITY_NS}editor/{safe_ts}'
    agent_uri = f'{AGENT_NS}{re.sub(r"[^0-9A-Za-z._-]", "_", editor)}'

    # Describe the graph itself as a prov:Entity, exactly as the generation
    # pipeline does for its claude/ and edcs/ graphs. This is what makes the
    # correction orderable: entity references carry no hmkia:generatedBy of
    # their own, so the time a value was asserted is read from the graph
    # holding it, via prov:wasGeneratedBy → prov:generatedAtTime.
    base_graphs = (payload.get('base_version') or {}).get('graphs') or []
    lines = [
        f'  <{graph_uri}> a <{PROV_NS}Entity> ;',
        f'    <{PROV_NS}wasGeneratedBy> <{act_uri}> ;',
        f'    <{EPIG_NS}interpretsInscription> <{BASE}inscription/{edcs_id}> ;',
    ]
    for base in base_graphs:
        lines.append(f'    <{PROV_NS}wasDerivedFrom> <{base}> ;')
    lines[-1] = lines[-1][:-2] + ' .'
    lines.append('')

    # Mirrors how the pipeline already records enrichment activities:
    # InterpretationUpdateAct + hasType/hasDate + prov:wasAssociatedWith.
    date_only = timestamp[:10]
    lines += [
        f'  <{act_uri}> a <{HMKIA_NS}InterpretationUpdateAct> ;',
        f'    <{HMKIA_NS}hasType> "manual_edit" ;',
        f'    <{HMKIA_NS}hasDate> "{date_only}"^^<{XSD_NS}date> ;',
        f'    <{EPIG_NS}activityType> "manual_edit" ;',
        f'    <{PROV_NS}wasAssociatedWith> <{agent_uri}> ;',
        f'    <{PROV_NS}generatedAtTime> "{timestamp}"^^<{XSD_NS}dateTime> .',
        '',
    ]

    # Chain this act to the corrections it supersedes, so the editorial history
    # is an ordered sequence of acts rather than a set of unrelated graphs.
    for prior in sorted(set((prior_acts or {}).values())):
        lines += [
            f'  <{act_uri}> <{HMKIA_NS}revises> <{prior}> .',
            '',
        ]

    lines += [
        f'  <{agent_uri}> a <{HMKIA_NS}HumanAgent> ;',
        f'    <{RDFS_NS}label> "{_esc(editor)}" .',
        '',
    ]

    for edit in edits:
        subject = edit['subject']
        predicate_iri = _expand(edit['predicate'])
        value = _literal(edit['new_value'], edit.get('datatype', 'xsd:string'))
        subject_type = edit.get('subject_type', '')

        if subject_type in VERSIONED_TYPES:
            # Statements are versioned: write a successor rather than mutating
            # the existing node, so the correction is auditable.
            new_uri = _next_version_uri(subject)
            lines += [
                f'  <{new_uri}> a <{EPIG_NS}{subject_type}> ;',
                f'    <{predicate_iri}> {value} ;',
                f'    <{PROV_NS}wasRevisionOf> <{subject}> ;',
                f'    <{HMKIA_NS}generatedBy> <{act_uri}> .',
                '',
            ]
        else:
            # Entity references are not versioned; record the corrected value
            # in the editor graph and attribute it to the editing act.
            lines += [
                f'  <{subject}> <{predicate_iri}> {value} ;',
                f'    <{HMKIA_NS}generatedBy> <{act_uri}> .',
                '',
            ]

    body = '\n'.join(lines)
    return f'INSERT DATA {{\n  GRAPH <{graph_uri}> {{\n{body}\n  }}\n}}'


# ── Payload validation ────────────────────────────────────────────────────────

REQUIRED_TOP = ('format_version', 'edcs_id', 'editor', 'edits')


def validate(payload: dict, path: Path) -> list:
    problems = []
    for key in REQUIRED_TOP:
        if key not in payload:
            problems.append(f'{path.name}: missing "{key}"')
    for i, edit in enumerate(payload.get('edits', [])):
        for key in ('subject', 'predicate', 'new_value'):
            if key not in edit:
                problems.append(f'{path.name}: edits[{i}] missing "{key}"')
        subject = edit.get('subject', '')
        if subject and not subject.startswith('http'):
            problems.append(f'{path.name}: edits[{i}] subject is not an IRI: {subject}')
        try:
            _expand(edit.get('predicate', ''))
        except ValueError as e:
            problems.append(f'{path.name}: edits[{i}] {e}')
    return problems


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description='Apply editor diff JSON to Fuseki as versioned corrections')
    parser.add_argument('files', nargs='+', help='edit diff JSON file(s)')
    parser.add_argument('--endpoint', default='http://54.92.185.36/himiko_epigraphy',
                        help='Fuseki dataset base URL')
    parser.add_argument('--user', default='admin')
    parser.add_argument('--password-env', default='FUSEKI_PASSWORD',
                        help='environment variable holding the password')
    parser.add_argument('--dry-run', action='store_true',
                        help='print the SPARQL UPDATE without sending it')
    parser.add_argument('--force', action='store_true',
                        help='apply even when the stored value differs from old_value')
    args = parser.parse_args()

    paths = [Path(f) for f in args.files]
    missing = [p for p in paths if not p.exists()]
    if missing:
        print('Error: file(s) not found: ' + ', '.join(str(p) for p in missing))
        return 1

    password = os.environ.get(args.password_env)
    if not password and not args.dry_run:
        password = getpass.getpass(f'Fuseki password for {args.user}: ')

    fuseki = None if args.dry_run else Fuseki(args.endpoint, args.user, password)

    total_applied = 0
    total_skipped = 0

    for path in paths:
        with open(path, encoding='utf-8') as f:
            payload = json.load(f)

        problems = validate(payload, path)
        if problems:
            print(f'FAIL {path.name}')
            for p in problems:
                print(f'  {p}')
            return 1

        edits = payload['edits']
        print(f'{path.name}: {len(edits)} edit(s) for {payload["edcs_id"]} '
              f'by {payload["editor"]}')

        applicable = edits
        if fuseki and not args.force:
            applicable = []
            for edit in edits:
                conflict = check_conflict(fuseki, edit)
                if conflict:
                    print(f'  SKIP (changed since load) {conflict}')
                    total_skipped += 1
                else:
                    applicable.append(edit)

        if not applicable:
            print('  nothing to apply')
            continue

        # Find the previous human correction to each property, if any, so the
        # new act can declare what it revises.
        prior_acts = {}
        if fuseki:
            for edit in applicable:
                prior = latest_edit_act(fuseki, edit['subject'],
                                        _expand(edit['predicate']))
                if prior:
                    prior_acts[f"{edit['subject']} {edit['predicate']}"] = prior

        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        update = build_update(payload, applicable, timestamp, prior_acts)

        if args.dry_run:
            print(update)
        else:
            try:
                fuseki.update(update)
            except urllib.error.HTTPError as e:
                print(f'  FAIL HTTP {e.code}: {e.read().decode("utf-8")[:200]}')
                return 1
            print(f'  applied {len(applicable)} edit(s)')
        total_applied += len(applicable)

    print()
    print(f'Applied : {total_applied}')
    print(f'Skipped : {total_skipped}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
