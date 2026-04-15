#!/usr/bin/env python3
"""
Fix missing required fields in modified_career_graphs and export to validated_career_graphs.

Fixes applied:
1. Old schema records (person_name at top level, no persons array)
   → Convert to new schema with persons/communities/person_relationships arrays
2. Missing ethnicity_evidence → fill with ""
3. Missing person_name_normalized / person_name_link → fill with ""

Usage:
    python fix_and_export.py                        # All places
    python fix_and_export.py --model claude
    python fix_and_export.py --places "Place1,Place2"
    python fix_and_export.py --dry-run              # Show stats without writing
"""

import json
import argparse
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent.parent
MODIFIED_DIR = SCRIPT_DIR / "modified_career_graphs"
OUTPUT_DIR = SCRIPT_DIR / "validated_career_graphs"
LOG_DIR = Path(__file__).parent / "logs"


# ── Fix functions ─────────────────────────────────────────────────────────────

def fix_old_schema(insc):
    """
    Convert old-schema record (person_name at top level) to new schema.
    These are all 'No Text' records — inscription text was absent.
    """
    person_name = insc.get("person_name", "No Text")
    person_name_readable = insc.get("person_name_readable", "No Text")
    has_career = insc.get("has_career", False)
    career_path = insc.get("career_path", [])
    notes = insc.get("notes", "")
    original_data = insc.get("original_data", {})

    new_insc = {
        "edcs_id": insc.get("edcs_id", ""),
        "persons": [
            {
                "person_id": 0,
                "person_name": person_name,
                "person_name_readable": person_name_readable,
                "praenomen": "",
                "nomen": "",
                "cognomen": "",
                "person_name_normalized": "",
                "person_name_link": "",
                "social_status": "",
                "social_status_evidence": "",
                "gender": "",
                "gender_evidence": "",
                "ethnicity": "",
                "ethnicity_evidence": "",
                "age_at_death": "",
                "age_at_death_evidence": "",
                "has_career": has_career,
                "career_path": career_path,
                "benefactions": [],
            }
        ],
        "communities": [],
        "person_relationships": [],
        "notes": notes,
        "original_data": original_data,
    }
    return new_insc, "old_schema_converted"


def fix_person_fields(person):
    """Fill missing string fields with empty string."""
    fixes = []
    for field in (
        "ethnicity", "ethnicity_evidence",
        "person_name_normalized", "person_name_link",
        "age_at_death", "age_at_death_evidence",
    ):
        if field not in person:
            person[field] = ""
            fixes.append(field)
    return fixes


def fix_relationship_fields(rel):
    """Fill missing relationship fields with defaults."""
    fixes = []
    if "target_community_id" not in rel:
        rel["target_community_id"] = None
        fixes.append("target_community_id")
    if "notes" not in rel:
        rel["notes"] = ""
        fixes.append("notes")
    return fixes


def fix_inscription(insc):
    """
    Apply all fixes to a single inscription record.
    Returns (fixed_insc, list_of_fixes_applied).
    """
    fixes = []

    # Fix 1: old schema
    if "persons" not in insc and "person_name" in insc:
        insc, tag = fix_old_schema(insc)
        fixes.append(tag)
        return insc, fixes

    # Fix 2: person-level missing fields
    persons = insc.get("persons", [])
    for i, person in enumerate(persons):
        for f in fix_person_fields(person):
            fixes.append(f"persons[{i}].{f}")

    # Fix 3: relationship-level missing fields
    for i, rel in enumerate(insc.get("person_relationships", [])):
        for f in fix_relationship_fields(rel):
            fixes.append(f"person_relationships[{i}].{f}")

    return insc, fixes


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fix and export validated career graphs")
    parser.add_argument("--model", "-m", default="claude")
    parser.add_argument("--places", "-p", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Show stats without writing files")
    args = parser.parse_args()

    model_dir = MODIFIED_DIR / args.model
    if not model_dir.exists():
        print(f"Error: directory not found: {model_dir}")
        return

    place_dirs = sorted([d for d in model_dir.iterdir() if d.is_dir()])
    if args.places:
        names = {p.strip() for p in args.places.split(",")}
        place_dirs = [d for d in place_dirs if d.name in names]
        if not place_dirs:
            print(f"No matching places found: {args.places}")
            return

    # Set up log
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"fix_export_{args.model}_{timestamp}.log"

    lines = []
    def log(msg):
        print(msg)
        lines.append(msg)

    run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log(f"Fix & Export started : {run_time}")
    log(f"Model                : {args.model}")
    log(f"Source               : {model_dir}")
    log(f"Output               : {OUTPUT_DIR / args.model}")
    log(f"Places               : {len(place_dirs)}")
    log(f"Dry run              : {args.dry_run}")
    log("=" * 70)

    total_inscriptions = 0
    total_fixed = 0
    fix_counts = {}

    for place_dir in place_dirs:
        for json_path in sorted(place_dir.glob("*.json")):
            try:
                with open(json_path, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                log(f"[ERROR] {json_path.name}: {e}")
                continue

            fixed_data = []
            file_fixes = 0

            for insc in data:
                fixed_insc, fixes = fix_inscription(insc)
                fixed_data.append(fixed_insc)
                if fixes:
                    file_fixes += len(fixes)
                    edcs_id = fixed_insc.get("edcs_id", "?")
                    log(f"  fixed {edcs_id}: {', '.join(fixes)}")
                    for f in fixes:
                        fix_counts[f] = fix_counts.get(f, 0) + 1

            total_inscriptions += len(data)
            total_fixed += file_fixes

            rel_path = json_path.relative_to(SCRIPT_DIR)
            status = f"({file_fixes} fixes)" if file_fixes else "(no fixes)"
            log(f"[ {'FIX' if file_fixes else ' OK'} ] {rel_path} {status}")

            if not args.dry_run:
                out_dir = OUTPUT_DIR / args.model / place_dir.name
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / json_path.name
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(fixed_data, f, ensure_ascii=False, indent=2)

    log("\n" + "=" * 70)
    log(f"Total inscriptions : {total_inscriptions}")
    log(f"Total fixes applied: {total_fixed}")
    log("\nFix breakdown:")
    for k, v in sorted(fix_counts.items(), key=lambda x: -x[1]):
        log(f"  {k}: {v}")
    if not args.dry_run:
        log(f"\nOutput saved to: {OUTPUT_DIR / args.model}")
    log(f"Log saved to    : {log_path}")

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
