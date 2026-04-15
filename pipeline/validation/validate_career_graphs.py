#!/usr/bin/env python3
"""
Validate career_graphs JSON files (modified or validated).

Usage:
    python validate_validated_career_graphs.py                            # Validate validated (default)
    python validate_validated_career_graphs.py --target modified          # Validate modified_career_graphs
    python validate_validated_career_graphs.py --target validated         # Validate validated_career_graphs
    python validate_validated_career_graphs.py --model claude
    python validate_validated_career_graphs.py --places "Place1,Place2"
    python validate_validated_career_graphs.py --summary                  # Show summary only
    python validate_validated_career_graphs.py --output report.json       # Save report to JSON
"""

import json
import argparse
import logging
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.parent
LOG_DIR = Path(__file__).parent / "logs"

# ── Controlled vocabularies ─────────────────────────────────────────────────

VALID_GENDERS = {"male", "female", "unknown", ""}
VALID_ETHNICITIES = {"Roman", "Roman with local name", "local", "", "unknown", "other"}
VALID_POSITION_TYPES = {
    "military", "other",
    "local-administration", "provincial-administration",
    "imperial-administration", "local-priesthood", "provincial-priesthood",
    "imperial-priesthood", "economic", "occupation"
}
VALID_BENEFACTION_TYPES = {
    "construction", "repair", "donation", "games", "feast", "other", "", "statue", "dedication"
}
VALID_RELATIONSHIP_TYPES = {
    "family", "colleague", "patronage", "dedication", "economic", "affiliation", "other"
}
VALID_COST_UNITS = {"sesterces", "denarii", None}


# ── Field-level validators ────────────────────────────────────────────────────

def check_field(errors, path, obj, field, expected_type, required=True, allowed_values=None):
    if field not in obj:
        if required:
            errors.append(f"{path}: missing required field '{field}'")
        return
    val = obj[field]
    if val is None and not required:
        return
    if expected_type == "number_or_null":
        if val is not None and not isinstance(val, (int, float)):
            errors.append(f"{path}.{field}: expected number or null, got {type(val).__name__} ({val!r})")
        return
    if expected_type == "bool_or_null":
        if val is not None and not isinstance(val, bool):
            errors.append(f"{path}.{field}: expected bool or null, got {type(val).__name__} ({val!r})")
        return
    if not isinstance(val, expected_type):
        errors.append(f"{path}.{field}: expected {expected_type.__name__}, got {type(val).__name__} ({val!r})")
        return
    if allowed_values is not None and val not in allowed_values:
        errors.append(f"{path}.{field}: invalid value {val!r} (allowed: {sorted(str(v) for v in allowed_values)})")


def validate_career_position(errors, path, pos):
    check_field(errors, path, pos, "position", str)
    check_field(errors, path, pos, "position_normalized", str)
    check_field(errors, path, pos, "position_abstract", str)
    check_field(errors, path, pos, "position_type", str, allowed_values=VALID_POSITION_TYPES)
    check_field(errors, path, pos, "position_description", str)
    check_field(errors, path, pos, "order", int)


def validate_benefaction(errors, path, benef):
    check_field(errors, path, benef, "benefaction_type", str, allowed_values=VALID_BENEFACTION_TYPES)
    check_field(errors, path, benef, "object", str)
    check_field(errors, path, benef, "object_type", str)
    check_field(errors, path, benef, "object_description", str)
    check_field(errors, path, benef, "benefaction_text", str)
    check_field(errors, path, benef, "cost", str)
    check_field(errors, path, benef, "notes", str)
    if "cost_numeric" in benef:
        check_field(errors, path, benef, "cost_numeric", "number_or_null", required=False)
    if "cost_unit" in benef:
        if benef["cost_unit"] not in VALID_COST_UNITS:
            errors.append(f"{path}.cost_unit: invalid value {benef['cost_unit']!r}")
    if "cost_original" in benef:
        check_field(errors, path, benef, "cost_original", str, required=False)
    if "cost_conversion_reasoning" in benef:
        check_field(errors, path, benef, "cost_conversion_reasoning", str, required=False)


def validate_person(errors, path, person, simplified=False):
    check_field(errors, path, person, "person_id", int)
    check_field(errors, path, person, "person_name", str)
    check_field(errors, path, person, "person_name_readable", str)
    check_field(errors, path, person, "praenomen", str)
    check_field(errors, path, person, "nomen", str)
    check_field(errors, path, person, "cognomen", str)
    check_field(errors, path, person, "person_name_normalized", str)
    check_field(errors, path, person, "person_name_link", str)
    check_field(errors, path, person, "social_status", str)
    check_field(errors, path, person, "social_status_evidence", str)
    check_field(errors, path, person, "gender", str, allowed_values=VALID_GENDERS)
    check_field(errors, path, person, "gender_evidence", str)
    check_field(errors, path, person, "ethnicity", str, allowed_values=VALID_ETHNICITIES)
    check_field(errors, path, person, "ethnicity_evidence", str)

    if not simplified:
        check_field(errors, path, person, "has_career", bool)

        if "age_at_death" in person:
            v = person["age_at_death"]
            """
            if v is not None and v != "" and not isinstance(v, (int, float)):
                errors.append(
                    f"{path}.age_at_death: expected int, empty string or null, "
                    f"got {type(v).__name__} ({v!r})"
                )
            """

        if "career_path" not in person:
            errors.append(f"{path}: missing required field 'career_path'")
        else:
            if not isinstance(person["career_path"], list):
                errors.append(f"{path}.career_path: expected list")
            else:
                for i, pos in enumerate(person["career_path"]):
                    validate_career_position(errors, f"{path}.career_path[{i}]", pos)

        if "benefactions" not in person:
            errors.append(f"{path}: missing required field 'benefactions'")
        else:
            if not isinstance(person["benefactions"], list):
                errors.append(f"{path}.benefactions: expected list")
            else:
                for i, benef in enumerate(person["benefactions"]):
                    validate_benefaction(errors, f"{path}.benefactions[{i}]", benef)
    else:
        if "career_path" in person and isinstance(person["career_path"], list):
            for i, pos in enumerate(person["career_path"]):
                validate_career_position(errors, f"{path}.career_path[{i}]", pos)
        if "benefactions" in person and isinstance(person["benefactions"], list):
            for i, benef in enumerate(person["benefactions"]):
                validate_benefaction(errors, f"{path}.benefactions[{i}]", benef)

    if "divinity" in person:
        check_field(errors, path, person, "divinity", bool, required=False)
    if "divinity_type" in person:
        if person["divinity_type"] is not None and not isinstance(person["divinity_type"], str):
            errors.append(f"{path}.divinity_type: expected string or null")
    if "divinity_classification_reasoning" in person:
        check_field(errors, path, person, "divinity_classification_reasoning", str, required=False)


def validate_community(errors, path, comm):
    check_field(errors, path, comm, "community_id", int)
    check_field(errors, path, comm, "community_name", str)
    check_field(errors, path, comm, "community_name_normalized", str)
    check_field(errors, path, comm, "community_type", str)
    check_field(errors, path, comm, "community_description", str)
    check_field(errors, path, comm, "evidence", str)


def validate_relationship(errors, path, rel):
    check_field(errors, path, rel, "source_person_id", int)
    check_field(errors, path, rel, "type", str, allowed_values=VALID_RELATIONSHIP_TYPES)
    check_field(errors, path, rel, "property", str)
    check_field(errors, path, rel, "property_text", str)
    check_field(errors, path, rel, "notes", str)
    for f in ("target_person_id", "target_community_id"):
        if f in rel:
            v = rel[f]
            if v is not None and not isinstance(v, int):
                errors.append(f"{path}.{f}: expected int or null, got {type(v).__name__} ({v!r})")


def validate_inscription(errors, path, insc):
    check_field(errors, path, insc, "edcs_id", str)

    # Old schema check — should not appear in validated data
    if "persons" not in insc and "person_name" in insc:
        errors.append(
            f"{path}: old schema detected — 'persons' array missing, 'person_name' found at top level"
        )
        return

    persons_list = insc.get("persons", [])
    simplified = isinstance(persons_list, list) and len(persons_list) > 20

    if "persons" not in insc:
        errors.append(f"{path}: missing required field 'persons'")
    else:
        if not isinstance(insc["persons"], list):
            errors.append(f"{path}.persons: expected list")
        else:
            for i, person in enumerate(insc["persons"]):
                validate_person(errors, f"{path}.persons[{i}]", person, simplified=simplified)

    if "communities" not in insc:
        errors.append(f"{path}: missing required field 'communities'")
    elif not isinstance(insc["communities"], list):
        errors.append(f"{path}.communities: expected list")
    else:
        for i, comm in enumerate(insc["communities"]):
            validate_community(errors, f"{path}.communities[{i}]", comm)

    if "person_relationships" not in insc:
        errors.append(f"{path}: missing required field 'person_relationships'")
    elif not isinstance(insc["person_relationships"], list):
        errors.append(f"{path}.person_relationships: expected list")
    else:
        for i, rel in enumerate(insc["person_relationships"]):
            validate_relationship(errors, f"{path}.person_relationships[{i}]", rel)

    if "notes" in insc and insc["notes"] is not None:
        if not isinstance(insc["notes"], str):
            errors.append(f"{path}.notes: expected string or null")


def validate_file(json_path):
    errors = []
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return [f"JSON parse error: {e}"], 0
    except IOError as e:
        return [f"File read error: {e}"], 0

    if not isinstance(data, list):
        return ["Root element must be a JSON array"], 0

    for i, insc in enumerate(data):
        edcs_id = insc.get("edcs_id", f"index[{i}]")
        validate_inscription(errors, f"[{i}] ({edcs_id})", insc)

    return errors, len(data)


# ── Logger ────────────────────────────────────────────────────────────────────

def setup_logger(log_path):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("final_validator")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    fmt = logging.Formatter("%(message)s")
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Validate career_graphs JSON files (modified or validated)"
    )
    parser.add_argument("--target", "-t", default="validated", choices=["modified", "validated"],
                        help="Target directory: 'modified' or 'validated' (default: validated)")
    parser.add_argument("--model", "-m", default="claude")
    parser.add_argument("--places", "-p", default=None, help="Comma-separated place names")
    parser.add_argument("--summary", "-s", action="store_true", help="Show summary only")
    parser.add_argument("--output", "-o", default=None,
                        help="Save report to JSON file (default: modified_report.json or validated_report.json)")
    args = parser.parse_args()

    target_dir = SCRIPT_DIR / f"{args.target}_career_graphs"
    model_dir = target_dir / args.model
    if not model_dir.exists():
        print(f"Error: directory not found: {model_dir}")
        return

    default_output = f"{args.target}_report.json"
    output_path = args.output if args.output else default_output

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_prefix = "final_validation" if args.target == "validated" else "validation"
    log_path = LOG_DIR / f"{log_prefix}_{args.model}_{timestamp}.log"
    logger = setup_logger(log_path)

    place_dirs = sorted([d for d in model_dir.iterdir() if d.is_dir()])
    if args.places:
        names = {p.strip() for p in args.places.split(",")}
        place_dirs = [d for d in place_dirs if d.name in names]
        if not place_dirs:
            logger.error(f"No matching places found: {args.places}")
            return

    run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"Validation started       : {run_time}")
    logger.info(f"Target                   : {args.target}_career_graphs")
    logger.info(f"Model                    : {args.model}")
    logger.info(f"Target directory         : {model_dir}")
    logger.info(f"Places                   : {len(place_dirs)}")
    logger.info(f"Log file                 : {log_path}")
    logger.info("=" * 70)

    total_files = 0
    total_inscriptions = 0
    total_errors = 0
    files_with_errors = 0
    report = []

    for place_dir in place_dirs:
        for json_path in sorted(place_dir.glob("*.json")):
            errors, count = validate_file(json_path)
            total_files += 1
            total_inscriptions += count
            total_errors += len(errors)
            rel_path = json_path.relative_to(SCRIPT_DIR)

            report.append({
                "file": str(rel_path),
                "inscriptions": count,
                "error_count": len(errors),
                "errors": errors,
            })

            if errors:
                files_with_errors += 1
                if not args.summary:
                    logger.info(f"\n[FAIL] {rel_path}  ({count} inscriptions, {len(errors)} errors)")
                    for e in errors:
                        logger.info(f"  ✗ {e}")
                else:
                    logger.info(f"[FAIL] {rel_path}  ({count} inscriptions, {len(errors)} errors)")
            else:
                logger.info(f"[ OK ] {rel_path}  ({count} inscriptions)")

    logger.info("\n" + "=" * 70)
    logger.info(f"Files validated    : {total_files}")
    logger.info(f"Total inscriptions : {total_inscriptions}")
    logger.info(f"Files with errors  : {files_with_errors} / {total_files}")
    logger.info(f"Total errors       : {total_errors}")
    if total_errors == 0:
        logger.info("✓ All files passed validation")
    logger.info(f"Log saved to       : {log_path}")

    out_path = Path(output_path)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "run_time": run_time,
            "target": args.target,
            "model": args.model,
            "total_files": total_files,
            "total_inscriptions": total_inscriptions,
            "files_with_errors": files_with_errors,
            "total_errors": total_errors,
            "files": report,
        }, f, ensure_ascii=False, indent=2)
    logger.info(f"JSON report saved  : {out_path}")


if __name__ == "__main__":
    main()
