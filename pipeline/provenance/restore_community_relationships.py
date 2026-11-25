"""再抽出で失われた共同体との関係を、抽出時のスナップショットから戻す.

reextract_relationships.py（現存しない）は person_relationships を人物間の関係
だけで作り直したため、人物 → 共同体の関係（target_community_id を持つもの）が
すべて落ちた。抽出時の値は _provenance.snapshots に残っているので、そこから
共同体を参照する関係だけを現在の person_relationships の末尾に戻す。

- 末尾に追加するので、既存の関係の位置（RDF の relationship/{i}）は変わらない。
- 戻した関係には generated_by_activity（元の抽出 activity）を付ける。
  create_rdf_himiko.py はこれを見て、再抽出の v1 ではなく抽出の v0 として出す。
- 戻した操作は restore_community_relationships の activity として記録する。
- 既に同じ関係（source, target_person, target_community, property が同じ）が
  ある場合は戻さない。2回実行しても結果は変わらない。

usage:
    python3 restore_community_relationships.py            # dry-run
    python3 restore_community_relationships.py --apply
"""
import argparse
import copy
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CORPUS = SCRIPT_DIR / "validated_career_graphs" / "claude"
SCRIPT_NAME = "restore_community_relationships.py"
ACTIVITY_TYPE = "restore_community_relationships"


def rel_key(r):
    return (r.get("source_person_id"), r.get("target_person_id"),
            r.get("target_community_id"), r.get("property"))


def restore_record(record, activity):
    """Return the number of relationships restored into record."""
    prov = record.get("_provenance") or {}
    acts = prov.get("activities", [])
    if not any(a.get("type") == "reextract_relationships" for a in acts):
        return 0
    snaps = [s for s in prov.get("snapshots", [])
             if s.get("field") == "person_relationships"]
    if not snaps:
        return 0
    snap = snaps[-1]
    current = record.get("person_relationships") or []
    have = {rel_key(r) for r in current}
    restored = []
    for r in snap.get("value") or []:
        if r.get("target_community_id") is None or rel_key(r) in have:
            continue
        r = copy.deepcopy(r)
        r["generated_by_activity"] = snap["generated_by_activity"]
        restored.append(r)
        have.add(rel_key(r))
    if not restored:
        return 0
    record["person_relationships"] = current + restored
    record["relationships"] = copy.deepcopy(record["person_relationships"])
    act = dict(activity, restored_count=len(restored),
               restored_from_activity=snap["generated_by_activity"])
    acts.append(act)
    return len(restored)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    ap.add_argument("--apply", action="store_true", help="JSON に書き込む")
    ap.add_argument("--report", help="集計を JSON で書き出す")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    activity = {
        "activity_id": f"{ACTIVITY_TYPE}-{now.strftime('%Y-%m-%dT%H%M%SZ')}",
        "script": SCRIPT_NAME,
        "type": ACTIVITY_TYPE,
        "model_type": "none",
        "model_id": "none",
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": ("reextract_relationships で落ちた共同体との関係を "
                 "_provenance.snapshots から戻した"),
    }

    stats = Counter()
    changed = []
    for path in sorted(Path(args.corpus).glob("*/*/*_career.json")):
        data = json.load(open(path, encoding="utf-8"))
        n_file = 0
        for record in data:
            n = restore_record(record, activity)
            if n:
                stats["records"] += 1
                stats["relationships"] += n
                n_file += n
        if n_file:
            changed.append(str(path.relative_to(args.corpus)))
            if args.apply:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"戻した関係: {stats['relationships']} 件 / "
          f"{stats['records']} 碑文 / {len(changed)} ファイル")
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump({"activity_id": activity["activity_id"],
                       "applied": args.apply, "stats": dict(stats),
                       "files": changed}, f, ensure_ascii=False, indent=1)
        print(f"report -> {args.report}")
    if not args.apply:
        print("\n書き込むには --apply を付けて再実行してください。")


if __name__ == "__main__":
    main()
