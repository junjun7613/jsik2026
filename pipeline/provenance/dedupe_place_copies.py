"""同じ碑文の重複コピーを1つに絞り、残りをコーパスの外へ移す.

batch_scrape_new_edcs.py は EDCS API の place（部分一致）で検索し、フォルダ名を
検索語から作っていた。そのため「Sid」で「Sidi …」の碑文がすべて入るなど、
同じ碑文が複数の地名フォルダに入り、フォルダごとに別々に抽出された。
create_rdf_himiko.py は主語 URI を EDCS ID と連番だけから作るので、重複コピーは
本番で同じノードに混ざる。

残すコピーは次の順で選ぶ（上が優先）:
  1. フォルダ名が original_data.place から作ったフォルダ名と一致する
  2. フォルダ名の語が place の語にすべて含まれる（"Sidi_Amar" ⊂ "Sidi Amar / Zurich"）
  3. 属州フォルダが original_data.province と一致する
  4. 適用済みの処理（activity の type）が多い
  5. 抽出（extract）が新しい
同じファイルに同じ碑文が2回入っている場合（63件）も同じ規則で1つにする。

除いたコピーは excluded_duplicates/<model>/<province>/<place>/<place>_career.json に
移し、manifest.json に「どこから除き、どれを残したか」を記録する。
すべての記録が除かれたファイルは削除し、空になったフォルダも削除する。

usage:
    python3 dedupe_place_copies.py            # dry-run
    python3 dedupe_place_copies.py --apply
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))
from batch_scrape_new_edcs import generate_folder_name  # noqa: E402

DEFAULT_CORPUS = SCRIPT_DIR / "validated_career_graphs" / "claude"
DEFAULT_OUT = SCRIPT_DIR / "excluded_duplicates" / "claude"


def tokens(name):
    return {t.lower() for t in re.split(r"_+", name) if t}


def rank(copy):
    """Sort key: larger is better."""
    rec, province, folder = copy["record"], copy["province"], copy["folder"]
    orig = rec.get("original_data") or {}
    want = generate_folder_name(orig.get("place", ""))
    acts = (rec.get("_provenance") or {}).get("activities", [])
    extract_ts = next((a.get("timestamp") or "" for a in acts
                       if a.get("type") == "extract"), "")
    return (
        folder == want,
        bool(tokens(folder)) and tokens(folder) <= tokens(want),
        province == (orig.get("province") or "").replace(" ", "_"),
        len({a.get("type") for a in acts}),
        extract_ts,
        -copy["order"],
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--apply", action="store_true", help="移動を実行する")
    ap.add_argument("--report", help="集計を JSON で書き出す")
    args = ap.parse_args()
    corpus, out = Path(args.corpus), Path(args.out)

    files = {}
    copies = defaultdict(list)
    order = 0
    for path in sorted(corpus.glob("*/*/*_career.json")):
        rel = path.relative_to(corpus)
        data = json.load(open(path, encoding="utf-8"))
        files[rel] = data
        for idx, rec in enumerate(data):
            copies[rec.get("edcs_id")].append({
                "rel": rel, "idx": idx, "record": rec, "order": order,
                "province": rel.parts[0], "folder": rel.parts[1],
            })
            order += 1

    drop = defaultdict(set)          # rel -> indices to remove
    manifest = []
    stats = Counter()
    for eid, cs in copies.items():
        if len(cs) < 2:
            continue
        cs = sorted(cs, key=rank, reverse=True)
        keep = cs[0]
        stats["inscriptions"] += 1
        stats[f"kept_by:{_reason(keep)}"] += 1
        keep_types = {a.get("type") for a in keep["record"]["_provenance"]["activities"]}
        for c in cs[1:]:
            drop[c["rel"]].add(c["idx"])
            lost = sorted({a.get("type") for a in c["record"]["_provenance"]["activities"]}
                          - keep_types)
            if lost:
                stats["excluded_with_extra_activity_types"] += 1
            manifest.append({
                "edcs_id": eid,
                "excluded_from": f"{c['rel']}#{c['idx']}",
                "kept": f"{keep['rel']}#{keep['idx']}",
                "kept_reason": _reason(keep),
                "same_file": c["rel"] == keep["rel"],
                "identical": c["record"] == keep["record"],
                "activity_types_only_in_excluded": lost,
            })
    stats["excluded_records"] = len(manifest)

    emptied = [rel for rel, ix in drop.items() if len(ix) == len(files[rel])]
    print(f"重複している碑文: {stats['inscriptions']}  除くコピー: {stats['excluded_records']}")
    for k in sorted(k for k in stats if k.startswith("kept_by:")):
        print(f"  残す理由 {k[8:]}: {stats[k]}")
    print(f"除くコピーにしかない処理がある: {stats['excluded_with_extra_activity_types']}")
    print(f"変更するファイル: {len(drop)}（うち全件除かれて削除: {len(emptied)}）")
    for rel in sorted(emptied):
        print(f"    削除: {rel}")

    if args.apply:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for rel, ix in drop.items():
            data = files[rel]
            removed = [r for i, r in enumerate(data) if i in ix]
            kept = [r for i, r in enumerate(data) if i not in ix]
            dest = out / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            prev = json.load(open(dest, encoding="utf-8")) if dest.exists() else []
            with open(dest, "w", encoding="utf-8") as f:
                json.dump(prev + removed, f, ensure_ascii=False, indent=2)
            path = corpus / rel
            if kept:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(kept, f, ensure_ascii=False, indent=2)
            else:
                path.unlink()
                if not any(path.parent.iterdir()):
                    path.parent.rmdir()
        mpath = out / "manifest.json"
        prev = json.load(open(mpath, encoding="utf-8")) if mpath.exists() else []
        with open(mpath, "w", encoding="utf-8") as f:
            json.dump(prev + [dict(m, excluded_at=now) for m in manifest],
                      f, ensure_ascii=False, indent=1)
        print(f"移動しました。manifest -> {mpath}")
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump({"stats": dict(stats), "emptied": [str(r) for r in emptied],
                       "manifest": manifest}, f, ensure_ascii=False, indent=1)
        print(f"report -> {args.report}")
    if not args.apply:
        print("\n移動するには --apply を付けて再実行してください。")


def _reason(copy):
    r = rank(copy)
    if r[0]:
        return "folder==place"
    if r[1]:
        return "folder⊂place"
    if r[2]:
        return "province"
    return "processing/extract"


if __name__ == "__main__":
    main()
