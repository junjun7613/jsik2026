"""
Controlled vocabularies for the format check, gathered from where they are
defined rather than copied by hand.

Sources:
  - network_analysis/mapping/status_category_map.json
        persons[].social_statuses[].category / subtype / rank / certainty
  - network_analysis/mapping/position_canonical_map.json
        persons[].career_path[].position_canonical / position_tier
  - network_analysis/mapping/object_category_map.json
        persons[].benefactions[].objects[].object_category / object_subtype
  - pipeline/prompt_template.py
        roman_emperors (person_name_normalized / person_name_link)

Vocabularies that exist only as prose inside the extraction prompt
(community_type, the standardized social_status labels) are listed here
verbatim. `check_prompt_sync()` confirms that each label still appears in the
prompt text, so a prompt edit that drops a label is caught.
"""

import json
import sys
from functools import lru_cache
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = PIPELINE_DIR.parent
MAPPING_DIR = PROJECT_DIR / "network_analysis" / "mapping"

# ── Vocabularies stated only in the extraction prompt ─────────────────────────
# pipeline/prompt_template.py, "COMMUNITY TYPES (controlled vocabulary ...)"
COMMUNITY_TYPES = {
    "legion", "cohort", "ala", "turma", "centuria", "vexillatio", "classis",
    "city", "municipium", "colonia", "vicus", "pagus", "provincia", "regio", "tribus",
    "collegium", "sodalitas", "corpus", "ordo", "familia", "templum",
    "populus", "other",
}

# pipeline/prompt_template.py, "STANDARDIZED SOCIAL STATUS LABELS"
# The raw social_status field is superseded by social_statuses[] (classify_social_status.py),
# so values outside this list are reported as warnings, not errors.
SOCIAL_STATUS_LABELS = {
    "emperor", "empress", "imperial-family",
    "senator-clarissimus", "senator-consularis", "senator-praetorius",
    "equestrian-perfectissimus", "equestrian-egregius", "equestrian-splendidus", "equestrian",
    "decurio", "duovir", "aedilis", "quaestor", "municipal-magistrate",
    "legatus", "tribunus", "centurio", "soldier", "veteran",
    "freedman", "freedwoman", "slave", "freeborn",
    "flamen", "pontifex", "augur", "sacerdos",
    "merchant", "medicus", "gladiator", "actor", "artisan",
    "unknown", "citizen", "",
}

# enrich_career_graphs.py (vital_events pass)
LIFE_EVENT_TYPES = {"birth", "death"}
DEATH_PLACE_SOURCES = {"text_explicit", "findspot_inferred", None}

# classify_social_status.py
STATUS_CERTAINTY = {"explicit", "inferred"}


def _collect(obj, key, out):
    """Collect every value stored under `key` anywhere in a nested JSON tree."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key and isinstance(v, str):
                out.add(v)
            else:
                _collect(v, key, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect(v, key, out)
    return out


def _load(name):
    with open(MAPPING_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def _keys(d):
    return {k for k in d if not k.startswith("$")}


@lru_cache(maxsize=1)
def load_vocab():
    status = _load("status_category_map.json")
    position = _load("position_canonical_map.json")
    obj = _load("object_category_map.json")

    sys.path.insert(0, str(PIPELINE_DIR))
    from prompt_template import roman_emperors  # noqa: E402

    return {
        "status_category": _keys(status["categories"]),
        "status_subtype": _collect(status, "subtype", set()),
        "status_rank": _collect(status, "rank", set()),
        "position_tier": _keys(position["tiers"]),
        "position_canonical": _collect({"o": position["offices"], "t": position["titles"]},
                                       "canonical", set()),
        "object_category": _keys(obj["categories"]),
        "object_subtype": _collect(obj, "subtype", set()),
        "emperor_names": set(roman_emperors),
        "emperor_qids": set(roman_emperors.values()),
        "emperor_by_name": dict(roman_emperors),
    }


def check_prompt_sync():
    """Return labels listed here that no longer appear in the extraction prompt."""
    text = (PIPELINE_DIR / "prompt_template.py").read_text(encoding="utf-8")
    labels = (COMMUNITY_TYPES | SOCIAL_STATUS_LABELS) - {""}
    return sorted(l for l in labels if f'"{l}"' not in text)


if __name__ == "__main__":
    v = load_vocab()
    for k, s in v.items():
        if isinstance(s, set):
            print(f"{k:20s} {len(s):4d}  {sorted(s)[:8]}")
    missing = check_prompt_sync()
    print("prompt sync:", "OK" if not missing else f"missing from prompt: {missing}")
