#!/usr/bin/env python3
"""Phase 3: 機械規則で確定しなかった寄進対象を LLM で分類する.

classify_object_category.py（Phase 1）が object_category_source="pending_llm"
を付けた要素のみを対象とし、benefaction_text（ラテン語原文）を根拠として
渡して第1階層 category と第2階層 subtype を判定させる。

Phase 1 と同じ3フィールドに書き込むが、object_category_source は "llm" と
するため、機械規則による分類と文脈解釈による分類を事後に区別できる。
_provenance にも Phase 1 とは別の活動として登録する。

設計上の判断:

- 統制語彙はプロンプトに全件列挙し、語彙外の値は呼び出し後に検証して弾く。
  LLM が新カテゴリを発明すると統制語彙の意味が失われるため。
- 確信が持てない場合は unknown.illegible を返させる。無理に具体カテゴリを
  当てさせると、史料に書かれていない情報を捏造することになる。
- subtype は null を許す。第1階層だけ確定して第2階層が決まらない場合、
  無理な細分より欠損の方が正確（OBJECT_TYPE_INVENTORY.md §7-0 運用規則）。
- 同一の (表層形, object_type, benefaction_text) はキャッシュして再利用する。

仕様: network_analysis/OBJECT_TYPE_INVENTORY.md §7
"""
import argparse
import collections
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
MAP_PATH = REPO_ROOT / "network_analysis/mapping/object_category_map.json"
DEFAULT_CORPUS = SCRIPT_DIR / "validated_career_graphs" / "claude"

SCRIPT_NAME = "classify_object_category_llm.py"
ACTIVITY_TYPE = "classify_object_category_llm"
GENERATED_FIELDS = [
    "benefactions[].objects[].object_category",
    "benefactions[].objects[].object_subtype",
    "benefactions[].objects[].object_category_source",
]

MODEL_ID = "claude-sonnet-4-5-20250929"
BATCH_SIZE = 20
PENDING_MARK = "pending_llm"


def now_compact():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── 統制語彙 ──────────────────────────────────────────────────────────────────

def build_vocabulary(spec):
    """マッピング表から (第1階層集合, category -> [subtype]) を組み立てる."""
    cats = list(spec["categories"])
    subs = collections.defaultdict(set)

    def note(d):
        if isinstance(d, dict) and d.get("category") and d.get("subtype"):
            subs[d["category"]].add(d["subtype"])

    for v in spec["ambiguous_forms"].values():
        note(v)
    for r in spec["surface_rules"]:
        note(r)
    for v in spec["object_type_direct"].values():
        note(v)
    return cats, {c: sorted(subs[c]) for c in cats}


def vocabulary_block(cats, subs, spec):
    lines = []
    for c in cats:
        lines.append(f'- {c} — {spec["categories"][c]}')
        for s in subs.get(c, []):
            lines.append(f'    {s}')
    return "\n".join(lines)


# ── プロンプト ────────────────────────────────────────────────────────────────

PROMPT_HEADER = """You are an expert in Roman epigraphy.

For each numbered item below, classify the object of a benefaction recorded in a
Latin inscription. Use the Latin source text as your evidence.

Controlled vocabulary — you MUST choose `category` from the top-level entries and
`subtype` from the indented entries belonging to that category:

{vocab}

Rules:
- `category` is REQUIRED. Choose exactly one of the {ncat} top-level values.
- `subtype` is OPTIONAL. Use null when the source does not determine which
  subtype applies. Do not guess a subtype to appear precise.
- If the text is damaged, illegible, or records only a verb with no object,
  use category "unknown" (subtype "unknown.illegible", or "unknown.verb_only"
  when only a verb such as fecit/posuit survives).
- If the source records only a generic word (monumentum, memoria) without
  indicating whether it is a tomb, building or statue, use
  category "monument", subtype "monument.unspecified".
- If it records only votum/sacrum/donum, use category "offering",
  subtype "offering.unspecified".
- Never invent a category or subtype outside the vocabulary above.
- `reasoning` must be one short sentence citing the Latin evidence.

Return ONLY a JSON array, one entry per item, in the same order:
[{{"id": <number>, "category": "<value>", "subtype": "<value or null>", "reasoning": "<one sentence>"}}]
"""


def build_prompt(batch, vocab, ncat):
    parts = [PROMPT_HEADER.format(vocab=vocab, ncat=ncat), "\nItems:\n"]
    for n, item in enumerate(batch, 1):
        parts.append(f"{n}. object (Latin): {item['object']!r}")
        parts.append(f"   prior object_type (unreliable): {item['object_type']!r}")
        txt = (item.get("benefaction_text") or "").strip()
        if txt:
            parts.append(f"   source text: {txt[:400]!r}")
        parts.append("")
    return "\n".join(parts)


def call_claude(prompt, client, max_tokens):
    message = client.messages.create(
        model=MODEL_ID,
        max_tokens=max_tokens,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def parse_response(text, n):
    """JSON 配列を取り出す。壊れていれば None を返し、呼び出し側で再試行する."""
    t = re.sub(r"^```(?:json)?\s*", "", text.strip())
    t = re.sub(r"\s*```$", "", t).strip()
    try:
        data = json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", t, re.S)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(data, list) or len(data) != n:
        return None
    return data


def classify_batch(batch, client, cats, subs, vocab, stats, retries=2):
    """1バッチを分類し、[(category, subtype, reasoning) or None] を返す."""
    prompt = build_prompt(batch, vocab, len(cats))
    out = [None] * len(batch)
    for attempt in range(retries + 1):
        try:
            raw = call_claude(prompt, client, max_tokens=180 * len(batch) + 256)
        except Exception as e:
            stats["api_errors"] += 1
            if attempt == retries:
                return out
            time.sleep(2 ** attempt)
            continue
        data = parse_response(raw, len(batch))
        if data is None:
            stats["parse_errors"] += 1
            if attempt == retries:
                return out
            time.sleep(1)
            continue
        for i, entry in enumerate(data):
            if not isinstance(entry, dict):
                continue
            c = entry.get("category")
            s = entry.get("subtype")
            if c not in cats:
                # 語彙外。統制語彙の意味を保つため採用しない
                stats["vocab_rejected"] += 1
                continue
            if s in ("", "null", "None"):
                s = None
            if s is not None and s not in subs.get(c, []):
                # category は妥当だが subtype が語彙外 → 第1階層のみ採用
                stats["subtype_rejected"] += 1
                s = None
            out[i] = (c, s, (entry.get("reasoning") or "").strip()[:300])
        return out
    return out


# ── 収集・書き込み ────────────────────────────────────────────────────────────

def iter_pending(record):
    for p in record.get("persons", []):
        for b in (p.get("benefactions") or []):
            for o in (b.get("objects") or []):
                if o.get("object_category_source") == PENDING_MARK:
                    yield o, b


def register_activity(record, activity_id):
    prov = record.setdefault("_provenance", {})
    acts = prov.setdefault("activities", [])
    acts[:] = [a for a in acts if a.get("type") != ACTIVITY_TYPE]
    acts.append({
        "activity_id": activity_id,
        "script": SCRIPT_NAME,
        "type": ACTIVITY_TYPE,
        "model_id": MODEL_ID,
        "timestamp": now_iso(),
        "generated_fields": list(GENERATED_FIELDS),
    })


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


def main():
    ap = argparse.ArgumentParser(
        description="pending_llm の寄進対象を LLM で分類する（Phase 3）")
    ap.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    ap.add_argument("--apply", action="store_true",
                    help="実際に書き込む（既定は dry-run）")
    ap.add_argument("--limit", type=int,
                    help="先頭 N 件の pending のみ処理（試走用）")
    ap.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--report", help="判定結果を JSON で書き出す")
    args = ap.parse_args()

    with open(MAP_PATH, encoding="utf-8") as f:
        spec = json.load(f)
    cats, subs = build_vocabulary(spec)
    vocab = vocabulary_block(cats, subs, spec)

    # 1. 対象を集める
    files = sorted(Path(args.corpus).glob("*/*/*_career.json"))
    targets = []   # (path, idx_in_file, obj, benef)
    loaded = {}
    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[SKIP] {path.name}: {e}", file=sys.stderr)
            continue
        found = False
        for record in data:
            for o, b in iter_pending(record):
                targets.append((path, record, o, b))
                found = True
        if found:
            loaded[path] = data

    if args.limit:
        targets = targets[:args.limit]
    if not targets:
        print("pending_llm の対象がありません。Phase 1 を先に実行してください。")
        return 0

    print(f"対象 pending : {len(targets)} 件")
    print(f"語彙         : 第1階層 {len(cats)} / 第2階層 {sum(len(v) for v in subs.values())}")

    if not args.apply:
        print("\n=== DRY-RUN === (API 呼び出しなし・書き込みなし)")
        print(f"推定 API 呼び出し数: {-(-len(targets)//args.batch_size)} "
              f"(batch size {args.batch_size})")
        print("\n--- 送信される項目の例（先頭3件） ---")
        for _, _, o, b in targets[:3]:
            print(f"  object      : {o.get('object')!r}")
            print(f"  object_type : {o.get('object_type')!r}")
            print(f"  source text : {(b.get('benefaction_text') or '')[:120]!r}")
            print()
        print("実行するには --apply を付けてください（API キーが必要）。")
        return 0

    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY が設定されていません。"
              "環境変数か --api-key で指定してください。", file=sys.stderr)
        return 1
    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)

    activity_id = f"{ACTIVITY_TYPE}-{MODEL_ID}-{now_compact()}"
    stats = collections.Counter()
    cache = {}
    results = []

    # 2. バッチで分類
    nb = -(-len(targets) // args.batch_size)
    for bi in range(nb):
        chunk = targets[bi * args.batch_size:(bi + 1) * args.batch_size]
        batch, idx_map = [], []
        for j, (_, _, o, b) in enumerate(chunk):
            key = ((o.get("object") or "").strip().lower(),
                   o.get("object_type") or "",
                   (b.get("benefaction_text") or "")[:200])
            if key in cache:
                stats["cache_hits"] += 1
                continue
            batch.append({"object": o.get("object") or "",
                          "object_type": o.get("object_type") or "",
                          "benefaction_text": b.get("benefaction_text") or ""})
            idx_map.append((j, key))
        if batch:
            got = classify_batch(batch, client, cats, subs, vocab, stats)
            for (j, key), res in zip(idx_map, got):
                cache[key] = res
        print(f"  batch {bi+1}/{nb}  ({min((bi+1)*args.batch_size, len(targets))}"
              f"/{len(targets)})", flush=True)

    # 3. 結果を反映
    touched_records = set()
    for path, record, o, b in targets:
        key = ((o.get("object") or "").strip().lower(),
               o.get("object_type") or "",
               (b.get("benefaction_text") or "")[:200])
        res = cache.get(key)
        if res is None:
            stats["unresolved"] += 1
            continue
        c, s, why = res
        o["object_category"] = c
        if s:
            o["object_subtype"] = s
        else:
            o.pop("object_subtype", None)
        o["object_category_source"] = "llm"
        if why:
            o["object_category_reasoning"] = why
        stats["resolved"] += 1
        stats[f"cat:{c}"] += 1
        results.append({"object": o.get("object"), "category": c,
                        "subtype": s, "reasoning": why})
        rid = id(record)
        if rid not in touched_records:
            register_activity(record, activity_id)
            touched_records.add(rid)

    for path, data in loaded.items():
        write_atomic(path, data)

    print(f"\n=== APPLIED ===")
    print(f"activity_id : {activity_id}")
    print(f"解決        : {stats['resolved']} / {len(targets)}")
    print(f"未解決      : {stats['unresolved']}")
    print(f"キャッシュ命中: {stats['cache_hits']}")
    for k in ("api_errors", "parse_errors", "vocab_rejected", "subtype_rejected"):
        if stats[k]:
            print(f"{k:16}: {stats[k]}")
    print("\n--- 第1階層 ---")
    for k, v in sorted(((k[4:], v) for k, v in stats.items()
                        if k.startswith("cat:")), key=lambda x: -x[1]):
        print(f"{v:6d}  {k}")

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump({"activity_id": activity_id, "model": MODEL_ID,
                       "targets": len(targets), "stats": dict(stats),
                       "results": results}, f, ensure_ascii=False, indent=1)
        print(f"\nreport -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
