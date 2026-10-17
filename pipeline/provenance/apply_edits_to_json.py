#!/usr/bin/env python3
"""校訂差分（編集者が作成した JSON）を validated_career_graphs に反映する.

docs/EDIT_DIFF_SPEC.md v1.0 の差分ファイルを読み、対象レコードに適用する。

従来は校訂がブラウザ → Fuseki → JSON と往復していたため、書き戻しが滞ると
次の enrichment が未校訂値に対して走り、再取り込みで機械グラフが
タイムスタンプ勝負に勝ってしまう構造だった。本スクリプトは JSON を
単一の真実とし、RDF は create_rdf_himiko.py による一方向の派生物とする。

    edits/pending/   未反映（エディタの出力先）
        ↓ 本スクリプト
    edits/applied/<日付>/   反映済み
    edits/conflict/         競合により適用しなかったもの

競合検出は差分の old_value と現在値の照合による。Fuseki の
prov:generatedAtTime を参照していた旧方式はエンドポイントに依存するため、
JSON だけで完結する方式に置き換えた。差分作成後に enrichment や別の校訂が
同じ箇所を変更していれば、適用せず conflict/ へ退避する。

適用は差分の timestamp（編集した時刻）の古い順に行う:
    同じ碑文に複数の校訂者の差分があるとき、先に適用されたものが
    本体の値になり、残りは競合として conflict/ に回る。ファイル名順だと
    どちらが採られるかが編集者名のアルファベット順で決まってしまう。
    新しい方を自動で優先（後勝ち）にはしない。後の校訂者は先の校訂を
    見ずに書いており、上書きすると先の校訂が気づかれずに消えるため。

使い方:
    python3 apply_edits_to_json.py --dry-run
    python3 apply_edits_to_json.py --apply
    python3 apply_edits_to_json.py --apply --edits-dir /path/to/edits
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CORPUS = SCRIPT_DIR / "validated_career_graphs"
DEFAULT_EDITS = SCRIPT_DIR / "edits"

SCRIPT_NAME = "apply_edits_to_json.py"
ACTIVITY_TYPE = "manual_edit"
FORMAT_VERSION = "1.0"

# persons[0].social_statuses[1].subtype → [('persons',0),('social_statuses',1),('subtype',None)]
TOKEN_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)((?:\[\d+\])*)")
INDEX_RE = re.compile(r"\[(\d+)\]")

# value_history に残すべき EntityReference 属性。statement 系は _vN 版を持つため不要。
# create_rdf_himiko.HISTORY_FIELD_PREDICATE と対応する。
HISTORY_FIELDS = {
    "person_name", "person_name_readable", "praenomen", "nomen", "cognomen",
    "person_name_normalized", "gender", "gender_evidence", "ethnicity",
    "ethnicity_evidence", "social_status", "social_status_evidence",
    "age_at_death", "age_at_death_evidence",
    "community_name", "community_name_normalized", "community_type", "evidence",
}


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_compact():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")


# ── パス解析 ──────────────────────────────────────────────────────────────────

def parse_path(path):
    """'persons[0].social_statuses[1].subtype' を走査可能な段に分解する.

    返り値は [(key, [indices...]), ...]。添字は 0 以上の整数。
    """
    steps = []
    for part in path.split("."):
        m = TOKEN_RE.fullmatch(part)
        if not m:
            raise ValueError(f"パスを解釈できません: {path!r} (部分: {part!r})")
        key = m.group(1)
        idx = [int(i) for i in INDEX_RE.findall(m.group(2) or "")]
        steps.append((key, idx))
    if not steps:
        raise ValueError(f"空のパス: {path!r}")
    return steps


def resolve_parent(record, steps):
    """最終段の直前までたどり、(容器, 最終キー, 最終添字) を返す.

    容器は dict または list。最終添字が None なら dict のキー代入、
    整数なら list の要素操作を意味する。
    """
    cur = record
    for key, idx in steps[:-1]:
        if not isinstance(cur, dict) or key not in cur:
            raise KeyError(f"{key} が存在しません")
        cur = cur[key]
        for i in idx:
            if not isinstance(cur, list):
                raise KeyError(f"{key} は配列ではありません")
            if i >= len(cur):
                raise IndexError(f"{key}[{i}] は範囲外（長さ {len(cur)}）")
            cur = cur[i]

    key, idx = steps[-1]
    if not idx:
        return cur, key, None
    # 最後の添字だけ残し、途中の添字はたどる
    if not isinstance(cur, dict) or key not in cur:
        raise KeyError(f"{key} が存在しません")
    container = cur[key]
    for i in idx[:-1]:
        if i >= len(container):
            raise IndexError(f"{key}[{i}] は範囲外")
        container = container[i]
    if not isinstance(container, list):
        raise KeyError(f"{key} は配列ではありません")
    return container, key, idx[-1]


def read_path(record, steps):
    """パスの現在値を返す。存在しなければ KeyError/IndexError."""
    container, key, i = resolve_parent(record, steps)
    if i is None:
        if not isinstance(container, dict) or key not in container:
            raise KeyError(f"{key} が存在しません")
        return container[key]
    if i >= len(container):
        raise IndexError(f"{key}[{i}] は範囲外（長さ {len(container)}）")
    return container[i]


def field_label(path):
    """'persons[0].cognomen' → 'persons[].cognomen'（generated_fields 形式）."""
    return re.sub(r"\[\d+\]", "[]", path)


def history_path(path):
    """value_history 用のパス表記に変換する.

    create_rdf_himiko.HISTORY_PATH_RE は 'person/0.cognomen' を期待しており、
    差分の 'persons[0].cognomen' とは別形式。変換できない（EntityReference
    属性でない）場合は None を返す。
    """
    m = re.fullmatch(r"(persons|communities)\[(\d+)\]\.([A-Za-z0-9_]+)", path)
    if not m:
        return None
    kind = "person" if m.group(1) == "persons" else "community"
    if m.group(3) not in HISTORY_FIELDS:
        return None
    return f"{kind}/{m.group(2)}.{m.group(3)}"


# ── 検証 ──────────────────────────────────────────────────────────────────────

def validate_payload(payload, name):
    problems = []
    for k in ("format_version", "edcs_id", "source_file", "record_index",
              "editor", "timestamp", "edits"):
        if k not in payload:
            problems.append(f"{name}: '{k}' がありません")
    if payload.get("format_version") not in (None, FORMAT_VERSION):
        problems.append(f"{name}: 未知の format_version "
                        f"{payload.get('format_version')!r}")
    edits = payload.get("edits")
    if not isinstance(edits, list) or not edits:
        problems.append(f"{name}: edits が空です")
        return problems
    for i, e in enumerate(edits):
        op = e.get("op")
        if op not in ("replace", "add", "remove"):
            problems.append(f"{name}: edits[{i}] op が不正 {op!r}")
        if "path" not in e:
            problems.append(f"{name}: edits[{i}] path がありません")
        else:
            try:
                parse_path(e["path"])
            except ValueError as ex:
                problems.append(f"{name}: edits[{i}] {ex}")
        if op in ("replace", "remove") and "old_value" not in e:
            problems.append(f"{name}: edits[{i}] {op} に old_value が必要です")
        if op in ("replace", "add") and "new_value" not in e:
            problems.append(f"{name}: edits[{i}] {op} に new_value が必要です")
    return problems


def find_record(data, payload):
    """差分が対象とするレコードを特定する.

    record_index を優先し、edcs_id が一致しなければファイル全体を探す。
    同一 edcs_id が複数ある場合に備え、index を正とする。
    """
    idx = payload.get("record_index")
    edcs = payload.get("edcs_id")
    if isinstance(idx, int) and 0 <= idx < len(data):
        if data[idx].get("edcs_id") == edcs:
            return idx
    hits = [i for i, r in enumerate(data) if r.get("edcs_id") == edcs]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise LookupError(f"edcs_id {edcs} がファイル内に見つかりません")
    raise LookupError(f"edcs_id {edcs} が {len(hits)} 件あり、"
                      f"record_index {idx} では特定できません")


def check_conflicts(record, edits):
    """old_value と現在値を照合する。競合の説明を列挙して返す."""
    problems = []
    for e in edits:
        op, path = e["op"], e["path"]
        steps = parse_path(path)
        if op == "add":
            # 照合対象がないため、挿入位置が範囲内かだけ見る
            try:
                container, key, i = resolve_parent(record, steps)
            except (KeyError, IndexError) as ex:
                problems.append(f"{path}: {ex}")
                continue
            if i is None:
                problems.append(f"{path}: add は配列要素を指す必要があります")
            elif i > len(container):
                problems.append(f"{path}: 挿入位置が範囲外"
                                f"（長さ {len(container)}）")
            continue
        try:
            current = read_path(record, steps)
        except (KeyError, IndexError) as ex:
            problems.append(f"{path}: {ex}")
            continue
        if current != e["old_value"]:
            problems.append(
                f"{path}: 期待 {e['old_value']!r} / 実際 {current!r}")
    return problems


# ── 適用 ──────────────────────────────────────────────────────────────────────

def apply_edits(record, edits, activity, timestamp):
    """差分をレコードに適用する。適用した path の一覧を返す.

    配列への add/remove は、同一配列内で添字がずれないよう降順に処理する
    （仕様 §3.1）。差分の添字は「適用前の状態」を基準としているため。
    """
    try:
        from _provenance_utils import record_superseded_value
    except ImportError:
        record_superseded_value = None

    ordered = sorted(
        edits,
        key=lambda e: (
            e["op"] == "replace",             # 構造変更を先に
            -(parse_path(e["path"])[-1][1] or [-1])[-1],  # 添字は降順
        ),
    )

    applied = []
    for e in ordered:
        op, path = e["op"], e["path"]
        steps = parse_path(path)
        container, key, i = resolve_parent(record, steps)

        if op == "replace":
            old = read_path(record, steps)
            # 上書きされる値を value_history に残す。EntityReference 属性は
            # _vN 版を持たないため、ここで残さないと JSON からも RDF からも消える。
            hp = history_path(path)
            if hp and record_superseded_value:
                record_superseded_value(
                    record, path=hp, field_label=field_label(path),
                    old_value=old, superseded_by=activity,
                    superseded_at=timestamp)
            if i is None:
                container[key] = e["new_value"]
            else:
                container[i] = e["new_value"]
        elif op == "add":
            container.insert(i, e["new_value"])
        elif op == "remove":
            del container[i]
        applied.append(path)
    return applied


def make_activity(payload, applied, timestamp):
    return {
        "activity_id": f"{ACTIVITY_TYPE}-{payload['editor']}-{now_compact()}",
        "script": SCRIPT_NAME,
        "type": ACTIVITY_TYPE,
        "editor": payload["editor"],
        "timestamp": timestamp,
        "note": payload.get("note", ""),
        "source_diff": payload["_filename"],
        "generated_fields": sorted({field_label(p) for p in applied}),
    }


def write_atomic(path, data):
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def log_result(log_path, entry):
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def edit_order(path):
    """適用順の並べ替えキー。編集した時刻の古い順、同時刻はファイル名順。
    読めないファイルは先頭に置き、ループ内の検証で [不正] として報告させる。"""
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        ts = str(payload.get("timestamp") or "")
    except Exception:
        ts = ""
    return (ts, path.name)


def main():
    ap = argparse.ArgumentParser(
        description="校訂差分を validated_career_graphs に反映する")
    ap.add_argument("files", nargs="*",
                    help="差分ファイル（省略時は edits/pending/*.json）")
    ap.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    ap.add_argument("--edits-dir", default=str(DEFAULT_EDITS))
    ap.add_argument("--apply", action="store_true",
                    help="実際に書き込む（既定は dry-run）")
    args = ap.parse_args()

    corpus = Path(args.corpus)
    edits_dir = Path(args.edits_dir)
    pending = edits_dir / "pending"
    applied_dir = edits_dir / "applied" / datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conflict_dir = edits_dir / "conflict"
    log_path = edits_dir / "apply_log.jsonl"

    files = [Path(f) for f in args.files] if args.files else \
        list(pending.glob("*.json")) if pending.is_dir() else []
    files.sort(key=edit_order)
    if not files:
        print(f"適用対象の差分がありません（{pending}）")
        return 0

    n_ok = n_conf = n_bad = 0
    # 適用後の対象ファイルを保持する。dry-run では書き込まないため、
    # これが無いと同じ碑文への後続の差分が適用前の値と照合され、
    # --apply なら競合になるものが「適用」と表示される。
    corpus_cache = {}
    print(f"=== {'APPLY' if args.apply else 'DRY-RUN (書き込みなし)'} ===")
    print(f"対象: {len(files)} ファイル\n")

    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as e:
            print(f"[不正] {path.name}: 読み込めません: {e}")
            n_bad += 1
            continue
        payload["_filename"] = path.name

        problems = validate_payload(payload, path.name)
        if problems:
            print(f"[不正] {path.name}")
            for p in problems[:5]:
                print(f"        {p}")
            n_bad += 1
            continue

        target = corpus / payload["source_file"]
        if not target.exists():
            print(f"[不正] {path.name}: 対象ファイルがありません: {target}")
            n_bad += 1
            continue

        if target not in corpus_cache:
            with open(target, encoding="utf-8") as f:
                corpus_cache[target] = json.load(f)
        data = corpus_cache[target]
        try:
            ridx = find_record(data, payload)
        except LookupError as e:
            print(f"[不正] {path.name}: {e}")
            n_bad += 1
            continue
        record = data[ridx]

        conflicts = check_conflicts(record, payload["edits"])
        if conflicts:
            print(f"[競合] {path.name}")
            for c in conflicts[:5]:
                print(f"        {c}")
            n_conf += 1
            if args.apply:
                conflict_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(conflict_dir / path.name))
                log_result(log_path, {
                    "file": path.name, "result": "conflict",
                    "reason": conflicts[0], "timestamp": now_iso()})
            continue

        ts = now_iso()
        activity = make_activity(payload, [e["path"] for e in payload["edits"]], ts)
        applied = apply_edits(record, payload["edits"], activity, ts)
        activity["generated_fields"] = sorted({field_label(p) for p in applied})
        record.setdefault("_provenance", {}).setdefault("activities", []).append(activity)

        print(f"[適用] {path.name}  ({len(applied)} 件)")
        for p in applied[:4]:
            print(f"        {p}")
        n_ok += 1

        if args.apply:
            write_atomic(target, data)
            applied_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(applied_dir / path.name))
            log_result(log_path, {
                "file": path.name, "result": "applied",
                "edcs_id": payload["edcs_id"], "editor": payload["editor"],
                "edits": len(applied), "activity_id": activity["activity_id"],
                "timestamp": ts})

    print(f"\n適用 {n_ok} / 競合 {n_conf} / 不正 {n_bad}")
    if not args.apply:
        print("\n書き込むには --apply を付けて再実行してください。")
    return 0 if n_bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
