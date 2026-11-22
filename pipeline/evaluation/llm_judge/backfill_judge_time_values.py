#!/usr/bin/env python3
"""
One-off: add judge-time values to judge rows written before run_judge.py
recorded them (pilot02 and uthina01, 2026-11-22).

The values come from a copy of validated_career_graphs/claude taken while it
was still in the state the judges saw. For those two runs this is the backup
made immediately before position_canonical_map v1.1 was applied
(2026-11-22T06:36Z); nothing else changed the data between judging and then.

The old rows carry no input hash, so the copy cannot be checked against
them directly. As a consistency check, every issue whose path was valid at
judging time (path_valid, recorded then) must resolve in the copy; failures
are counted and reported, and the input hash is recorded from the copy.

Usage:
  python backfill_judge_time_values.py --run-id uthina01 --data-dir /path/to/backup/claude \
      --label "backup of validated_career_graphs/claude taken before ... (date)"
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from judge_common import RUNS_DIR, build_user_message, input_sha, load_record, value_map  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--data-dir", required=True, help="copy of validated_career_graphs/claude as judged")
    ap.add_argument("--label", required=True,
                    help="what the copy is, recorded in each row (not the local path, which is temporary)")
    args = ap.parse_args()
    data_dir = Path(args.data_dir)
    run_dir = RUNS_DIR / args.run_id

    for path in sorted(run_dir.glob("*.jsonl")):
        rows = [json.loads(l) for l in path.read_text().splitlines()]
        filled = unresolved = 0
        for r in rows:
            if "flagged_values" in r or r["status"] != "ok":
                continue
            rec = load_record(r["key"], data_dir=data_dir)
            vals = value_map(rec)
            r["input_sha"] = input_sha(build_user_message(rec))
            r["flagged_values"] = {i["path"]: vals.get(i["path"]) for i in r["result"].get("issues", [])}
            unresolved += sum(1 for i in r["result"].get("issues", [])
                              if i.get("path_valid") and i.get("verdict") != "omission"
                              and i["path"] not in vals and not any(k.startswith(i["path"]) for k in vals))
            r["flagged_values_backfilled_from"] = args.label
            filled += 1
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        print(f"{path.name}: filled {filled} rows; valid paths not found in the copy: {unresolved}")


if __name__ == "__main__":
    main()
