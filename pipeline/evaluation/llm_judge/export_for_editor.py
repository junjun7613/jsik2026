#!/usr/bin/env python3
"""
Export judge results for ai_epigraphy_editor, one file per place.

The editor loads a place's JSON from validated_career_graphs and, if this
export has a file for that place, shows the judges' findings next to the
fields they refer to. Records are matched by (place file, record index), the
same key the editor's edit diffs use.

Writes
------
  editor_export/manifest.json
      runs: run_id → judges and models, prompt hash, tier counts
      places: place path → run_ids that cover it
  editor_export/places/<province>/<place>.json
      runs: run_id → {records: {record_index: finding summary}}

Findings carry the value each flagged field had when it was judged
(`judged_value`); the editor compares it with the current data and marks
findings whose value has changed since.

Audit items keep their findings under `blind`; the editor reveals them only
after the reviewer has recorded a verdict.

The export is derived data and is regenerated after every run:

  python export_for_editor.py --run-id pilot02 --run-id uthina01

ai_epigraphy_editor reads it through the symlink data/judge → editor_export.
"""
import argparse
import json
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_review_queue import build_run  # noqa: E402
from judge_common import RUNS_DIR, LLM_JUDGE_DIR  # noqa: E402

OUT_DIR = LLM_JUDGE_DIR / "editor_export"

KEEP = ("tier", "consensus_verdict", "audit", "audit_origin", "rank", "score", "judge_status", "judge_overall",
        "judge_notes", "format_errors", "format_warnings", "flagged", "blind")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", action="append", required=True, dest="run_ids",
                    help="run to export (repeatable)")
    ap.add_argument("--judges", default="claude,gpt,gemini")
    ap.add_argument("--audit-n", type=int, default=None)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    judges = args.judges.split(",")

    places = defaultdict(lambda: {"runs": {}})
    manifest = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "runs": {}, "places": {}}

    for run_id in args.run_ids:
        meta = json.loads((RUNS_DIR / run_id / "run_meta.json").read_text())
        items, _, summary = build_run(run_id, judges, args.audit_n, args.seed)
        manifest["runs"][run_id] = {
            "judges": {j: meta["judges"][j]["model"] for j in judges if j in meta.get("judges", {})},
            "prompt_hash": meta.get("prompt_hash"),
            "prompt_version": meta.get("prompt_version"),
            "tiers": summary["tiers"],
            "targets": summary["targets"],
        }
        for it in items:
            place_path, idx = it["key"].rsplit("#", 1)
            run = places[place_path]["runs"].setdefault(run_id, {"records": {}})
            run["records"][idx] = {"edcs_id": it["edcs_id"], **{k: it[k] for k in KEEP if k in it}}
        print(f"{run_id}: {len(items)} records")

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    for place_path, body in places.items():
        province, place = place_path.split("/")[:2]
        out = OUT_DIR / "places" / province / f"{place}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"place_path": place_path, **body}, ensure_ascii=False))
        manifest["places"][place_path] = sorted(body["runs"])
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(f"{len(places)} places → {OUT_DIR}")


if __name__ == "__main__":
    main()
