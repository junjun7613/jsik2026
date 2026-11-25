"""
Shared pieces of the LLM-as-a-Judge evaluation.

What the judges see
-------------------
Every judge (Claude / GPT / Gemini) receives exactly the same material:

  system  = JUDGE_INSTRUCTIONS + extraction spec (the extraction prompt itself,
            minus the inscription) + post-extraction conventions
  user    = EDCS metadata + inscription text + the extraction, flattened to
            one `path = value` line per field

The extraction is flattened so that every judged item has an exact address.
Judges must cite those addresses; the aggregation step matches findings
across judges by path. The judges are not told which model produced the
extraction (blind).

What is judged
--------------
All fields produced after EDCS scraping: persons / communities /
person_relationships and everything nested in them, including the
rule-based classify_* outputs. Excluded:

  - original_data, edcs_id, bibliography_parsed  … EDCS metadata (shown as context)
  - _provenance                                  … bookkeeping
  - top-level person_name / career_path / relationships / social_status …
    a legacy mirror of persons[] (same values, older schema)

Bookkeeping and free-text explanation fields are shown as context but are
not judged (see CONTEXT_ONLY_KEYS).
"""

import hashlib
import json
import random
import re
import sys
from pathlib import Path

LLM_JUDGE_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = LLM_JUDGE_DIR.parent.parent
PROJECT_DIR = PIPELINE_DIR.parent
DATA_DIR = PIPELINE_DIR / "provenance" / "validated_career_graphs" / "claude"
RUNS_DIR = LLM_JUDGE_DIR / "runs"
CONFIG_PATH = LLM_JUDGE_DIR / "judge_config.json"

sys.path.insert(0, str(PIPELINE_DIR))
sys.path.insert(0, str(PIPELINE_DIR / "validation"))

PROMPT_VERSION = "judge-v1"

JUDGED_TOP_KEYS = ("persons", "communities", "person_relationships")

# Shown to the judge for context, never judged.
CONTEXT_ONLY_KEYS = {
    "person_id", "community_id",
    "divinity_classification_reasoning", "vital_events_reasoning",
    "cost_conversion_reasoning", "notes", "social_status_evidence_note",
    "property_text_note", "property_text_full",
    "social_status_source", "object_category_source", "position_canonical_source",
    "source", "needs_llm", "migrated_from",
}

# Inscriptions whose flattened extraction exceeds this many lines are not sent
# to the judges; they go to the review queue as `unjudged_large`.
MAX_LINES = 600


# ── Data access ───────────────────────────────────────────────────────────────

def iter_records(data_dir=DATA_DIR, include_duplicates=False):
    """Yield (key, record). key = '<relative file>#<index>'.

    The same EDCS-ID appears in several place files (place searches overlap:
    4,846 IDs as of 2026-11). By default only the first occurrence in sorted
    path order is judged.
    """
    seen = set()
    for f in sorted(data_dir.rglob("*.json")):
        rel = f.relative_to(data_dir).as_posix()
        with open(f, encoding="utf-8") as fh:
            data = json.load(fh)
        for i, rec in enumerate(data):
            eid = rec.get("edcs_id")
            if not include_duplicates:
                if eid in seen:
                    continue
                seen.add(eid)
            yield f"{rel}#{i}", rec


def load_record(key, data_dir=DATA_DIR):
    rel, idx = key.rsplit("#", 1)
    with open(data_dir / rel, encoding="utf-8") as fh:
        return json.load(fh)[int(idx)]


def sample_keys(n, seed, include_duplicates=False):
    keys = [k for k, _ in iter_records(include_duplicates=include_duplicates)]
    if n is None or n >= len(keys):
        return keys
    return sorted(random.Random(seed).sample(keys, n))


# ── Flattening ────────────────────────────────────────────────────────────────

def _fmt(v):
    return json.dumps(v, ensure_ascii=False)


def flatten(rec):
    """Return (lines, judged_paths, container_paths).

    lines            : 'path = value' strings in document order; context-only
                       fields are suffixed with '   (context)'.
    judged_paths     : leaf paths a judge may flag as incorrect/uncertain.
    container_paths  : list/object paths a judge may cite for an omission.
    """
    lines, judged, containers = [], set(), set()

    def walk(v, path, key):
        if isinstance(v, dict):
            containers.add(path)
            for k, sub in v.items():
                walk(sub, f"{path}.{k}", k)
        elif isinstance(v, list):
            containers.add(path)
            if not v:
                lines.append(f"{path} = []")
            for i, sub in enumerate(v):
                walk(sub, f"{path}[{i}]", key)
        else:
            if key in CONTEXT_ONLY_KEYS:
                lines.append(f"{path} = {_fmt(v)}   (context)")
            else:
                lines.append(f"{path} = {_fmt(v)}")
                judged.add(path)

    for top in JUDGED_TOP_KEYS:
        walk(rec.get(top, []), top, top)
    return lines, judged, containers


def value_map(rec):
    """{path: value as shown to the judge (JSON text)} for every leaf."""
    out = {}
    for line in flatten(rec)[0]:
        path, _, val = line.partition(" = ")
        out[path] = val.replace("   (context)", "")
    return out


# ── Classifying findings ──────────────────────────────────────────────────────
#
# Judges report problems only; a field nobody flags is "no finding", not
# "correct". A major-consensus field (major for >= 2 judges) can still mean
# different things: the judges agree it is wrong, agree they cannot tell, or
# agree something is missing. These are kept apart (docs/ASSESSMENT_STATUS_SPEC.md).

# Major-consensus verdict classes, most actionable first.
CONSENSUS_VERDICTS = ["incorrect", "mixed", "omission", "uncertain"]

# Per-field outcome of one judge run, worst first.
FIELD_OUTCOMES = ["major_incorrect", "major_mixed", "major_omission", "major_uncertain",
                  "major_single", "minor", "no_finding"]


def consensus_verdict(findings):
    """Verdict class of a field from {judge: {verdict, severity}}; None unless >= 2 call it major.

    incorrect / omission / uncertain when every judge calling it major gives
    that verdict, otherwise mixed.
    """
    major = [f["verdict"] for f in findings.values() if f.get("severity") == "major"]
    if len(major) < 2:
        return None
    kinds = set(major)
    return kinds.pop() if len(kinds) == 1 else "mixed"


def field_outcome(findings):
    """One of FIELD_OUTCOMES for a field, from {judge: {verdict, severity}} ({} = not flagged)."""
    cv = consensus_verdict(findings)
    if cv:
        return f"major_{cv}"
    if any(f.get("severity") == "major" for f in findings.values()):
        return "major_single"
    return "minor" if findings else "no_finding"


def value_shas(rec):
    """{judged leaf path: fingerprint} for the values the judge is shown.

    Stored with each judge row so compute_assessment_status.py can tell, field
    by field, whether a judgement still applies to the current value
    (docs/ASSESSMENT_STATUS_SPEC.md). Context-only fields are not judged and
    are left out.
    """
    sys.path.insert(0, str(PIPELINE_DIR / "provenance"))
    from _provenance_utils import leaf_fingerprints
    _, judged, _ = flatten(rec)
    fps = {}
    for top in JUDGED_TOP_KEYS:
        fps.update(leaf_fingerprints(rec.get(top, []), top))
    return {p: fps[p] for p in sorted(judged) if p in fps}


def input_sha(user_message):
    return hashlib.sha256(user_message.encode("utf-8")).hexdigest()[:16]


def inscription_header(rec):
    od = rec.get("original_data") or {}
    meta = {
        "EDCS-ID": rec.get("edcs_id"),
        "province": od.get("province"),
        "place (findspot)": od.get("place"),
        "dating": f"{od.get('dating_from', '')} – {od.get('dating_to', '')}".strip(" –"),
        "language": od.get("language"),
        "material": od.get("material"),
    }
    meta_lines = "\n".join(f"{k}: {v}" for k, v in meta.items() if v)
    return meta_lines, od.get("inscription", "")


def build_user_message(rec):
    lines, _, _ = flatten(rec)
    meta, text = inscription_header(rec)
    return (
        "## EDCS metadata (ground truth, not judged)\n"
        f"{meta}\n\n"
        "## Inscription text (as given to the extractor)\n"
        f"{text}\n\n"
        "## Extraction to review\n"
        "Each line is `path = value`. Lines marked (context) are not judged.\n\n"
        + "\n".join(lines)
    )


# ── System prompt ─────────────────────────────────────────────────────────────

JUDGE_INSTRUCTIONS = """You are an expert in Latin epigraphy reviewing a structured extraction made from one Roman inscription by an automated system. Your review decides which extractions a human epigraphist checks first, so precision matters more than coverage of trivia.

# Your task
Compare the extraction against the inscription text and report every field that is wrong, doubtful, or missing. Report problems only: any judged field you do not report is taken as correct.

For each problem give:
- path: the exact path as written in the extraction (e.g. `persons[0].career_path[2].position_type`). For an omission, cite the list or object the missing item belongs in (e.g. `persons[1].career_path`, `person_relationships`, `communities`), or `persons` for a missing person.
- verdict:
  - `incorrect` — the value contradicts the text or the conventions below.
  - `omission` — the text supports an item or value the extraction lacks.
  - `uncertain` — you cannot decide, typically because the text is fragmentary or the reading is disputed. Do not use it to hedge a clear judgement.
- severity:
  - `major` — changes what a historian would conclude: wrong or missing person, office, status, benefaction, relationship or its direction, gender, age, deity, a misidentified emperor.
  - `minor` — normalisation, spelling, English description wording, evidence quote slightly off, order of equivalent items.
- reason: one or two sentences citing the Latin that supports your judgement.
- suggested_value: the value you would put there, or an empty string if none.

Set `overall` to `acceptable` (no major problems), `has_errors` (at least one major problem), or `cannot_judge` (the text is too damaged to evaluate). Use `note` for anything that does not fit a single path; otherwise leave it empty.

# How to judge
- Judge against the conventions the extractor was given (the extraction specification below), not against your own preferred scheme. A value that follows the specification is correct even if you would have modelled it differently.
- Restorations in square brackets and expansions in parentheses are part of the text. Accept a reading the text plausibly supports; flag only readings it does not support.
- Evidence fields must quote the inscription verbatim (allowing for bracket and abbreviation marks). Flag an evidence field that paraphrases or quotes text that is not there.
- `property` in a relationship is the role of the SOURCE person. Check direction carefully.
- Consular dating formulas (ablative `... co(n)s(ulibus)`) are not career positions.
- Do not report a problem twice: if a whole item is wrong (e.g. a person who is not in the text), report it once at the item's path.
- Fields marked (context) are explanations or bookkeeping. Do not report them.
"""

POST_EXTRACTION_CONVENTIONS = """# Fields added after extraction

## Divinity (enrichment pass)
`divinity` is true when the named entity is a god, goddess, deified emperor (divus/diva) or deified abstraction (Genius, Fortuna, Victoria …). Humans with imperial titles such as Augustus are not divinities. `divinity_type` holds the main deity name without epithets, or null.

## Life events (enrichment pass)
`life_events[]` holds birth/death places. Birth place only when stated (origo, domo, natione). Death place: if the text states it, `place_source` = `text_explicit`; if the inscription is funerary (D.M., hic situs est, vixit annis …) and no place is stated, the findspot is used with `place_source` = `findspot_inferred`. Non-funerary inscriptions get no inferred death place.

## Benefaction cost (enrichment pass)
`cost_numeric` / `cost_unit` convert `cost` to a number in sesterces or denarii; null when no sum is stated.

## Rule-based classification (classify_* scripts)
These fields were assigned by deterministic rules from the values above. Judge whether the assigned class fits the person or object as the text describes it.
- `social_statuses[]`: one entry per status axis. `category` ∈ {categories}; `subtype` is `<category>.<x>`, one of {subtypes}; `rank` (only for ordo ranks) ∈ {ranks}; `certainty` is `explicit` when the text states the status and `inferred` when it is deduced from names, tribe or context; `evidence` quotes the text.
- `career_path[].position_type` additionally allows `title` for titles and powers that are not offices (imperator, tribunicia potestas, pater patriae, victory titles). `position_canonical` is a snake_case canonical office name; `position_tier` ∈ {tiers}.
- `benefactions[].objects[].object_category` ∈ {obj_categories}; `object_subtype` is `<category>.<x>`.
"""


def build_system_prompt():
    from prompt_template import build_extraction_prompt
    from vocab import load_vocab

    v = load_vocab()
    spec = build_extraction_prompt("<<INSCRIPTION>>")
    spec = spec[spec.index("Information to extract:"):]
    conv = POST_EXTRACTION_CONVENTIONS.format(
        categories=", ".join(sorted(v["status_category"])),
        subtypes=", ".join(sorted(v["status_subtype"])),
        ranks=", ".join(sorted(v["status_rank"])),
        tiers=", ".join(sorted(v["position_tier"])),
        obj_categories=", ".join(sorted(v["object_category"])),
    )
    return (
        JUDGE_INSTRUCTIONS
        + "\n# Extraction specification (the instructions the extractor received)\n\n"
        + spec
        + "\n\n" + conv
    )


def prompt_hash(system_prompt):
    return hashlib.sha256((PROMPT_VERSION + system_prompt).encode()).hexdigest()[:12]


# ── Output schema (shared by all three providers) ─────────────────────────────
# Kept to the subset every provider's strict JSON-schema mode accepts:
# no nullable types, no numeric bounds, all properties required.

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["incorrect", "omission", "uncertain"]},
                    "severity": {"type": "string", "enum": ["major", "minor"]},
                    "reason": {"type": "string"},
                    "suggested_value": {"type": "string"},
                },
                "required": ["path", "verdict", "severity", "reason", "suggested_value"],
                "additionalProperties": False,
            },
        },
        "overall": {"type": "string", "enum": ["acceptable", "has_errors", "cannot_judge"]},
        "note": {"type": "string"},
    },
    "required": ["issues", "overall", "note"],
    "additionalProperties": False,
}


def normalize_path(p):
    p = p.strip().strip("`").strip()
    p = re.sub(r"^\$\.?", "", p)
    return re.sub(r"\s+", "", p)


def check_paths(result, rec):
    """Annotate each issue with path_valid: does the cited path exist?"""
    _, judged, containers = flatten(rec)
    for iss in result.get("issues", []):
        p = normalize_path(iss.get("path", ""))
        iss["path"] = p
        if iss.get("verdict") == "omission":
            iss["path_valid"] = p in containers or p in judged
        else:
            iss["path_valid"] = p in judged or p in containers
    return result


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)
