#!/usr/bin/env python3
"""
Run the LLM-as-a-Judge over Claude extractions with three judge models.

The judge is deliberately not agentic: one fixed prompt, one call per
inscription, schema-constrained output. Every judge gets identical input.

Usage
-----
  # 1. Fix the target set (shared by all judges; written to runs/<id>/targets.json)
  python run_judge.py prepare --run-id pilot01 --sample 30 --seed 42
  python run_judge.py prepare --run-id full01 --all
  python run_judge.py prepare --run-id uthina01 --place Uthina
  python run_judge.py prepare --run-id pilot01_rep2 --copy-targets-from pilot01   # repeat run

  # 2. Estimate input tokens (uses Anthropic's free count_tokens endpoint)
  python run_judge.py estimate --run-id pilot01

  # 3. Run (resumable: completed keys are skipped)
  python run_judge.py run --run-id pilot01 --judges claude,gpt,gemini --workers 4

Output: runs/<run_id>/<judge>.jsonl, one line per inscription:
  {key, edcs_id, judge, model, status, result, usage, latency_s, timestamp, error}
  status ∈ ok | refusal | truncated | parse_error | api_error | skipped_large

This script never writes to validated_career_graphs or provenance/edits.
"""

import argparse
import json
import os
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from judge_common import (  # noqa: E402
    JUDGE_SCHEMA, MAX_LINES, PROJECT_DIR, PROMPT_VERSION, RUNS_DIR,
    build_system_prompt, build_user_message, check_paths, flatten,
    load_config, load_record, prompt_hash, sample_keys,
)


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_env():
    from dotenv import load_dotenv
    load_dotenv(PROJECT_DIR / ".env")


# ── Provider calls ────────────────────────────────────────────────────────────
# Each returns (status, parsed_or_None, usage_dict, raw_text, error_message).

def call_anthropic(client, cfg, system, user):
    import anthropic
    try:
        resp = client.messages.create(
            model=cfg["model"],
            max_tokens=cfg["max_tokens"],
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            # The installed SDK (0.75) predates the typed output_config parameter.
            extra_body={"output_config": {
                "effort": cfg["effort"],
                "format": {"type": "json_schema", "schema": JUDGE_SCHEMA},
            }},
        )
    except anthropic.BadRequestError as e:
        return "api_error", None, {}, "", f"400: {e.message}"
    except anthropic.APIStatusError as e:
        return "api_error", None, {}, "", f"{e.status_code}: {e.message}"
    except anthropic.APIConnectionError as e:
        return "api_error", None, {}, "", f"connection: {e}"

    u = resp.usage
    usage = {"input": u.input_tokens, "output": u.output_tokens,
             "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
             "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0}
    text = next((b.text for b in resp.content if b.type == "text"), "")
    if resp.stop_reason == "refusal":
        return "refusal", None, usage, text, str(getattr(resp, "stop_details", "") or "")
    if resp.stop_reason == "max_tokens":
        return "truncated", None, usage, text, "max_tokens"
    return parse(text, usage)


def call_openai(client, cfg, system, user):
    import openai
    try:
        resp = client.chat.completions.create(
            model=cfg["model"],
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            response_format={"type": "json_schema", "json_schema": {
                "name": "judge_result", "schema": JUDGE_SCHEMA, "strict": True}},
            reasoning_effort=cfg["reasoning_effort"],
            max_completion_tokens=cfg["max_completion_tokens"],
        )
    except openai.APIStatusError as e:
        return "api_error", None, {}, "", f"{e.status_code}: {e.message}"
    except openai.APIConnectionError as e:
        return "api_error", None, {}, "", f"connection: {e}"

    u = resp.usage
    cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
    usage = {"input": u.prompt_tokens - cached, "output": u.completion_tokens, "cache_read": cached}
    ch = resp.choices[0]
    if getattr(ch.message, "refusal", None):
        return "refusal", None, usage, "", ch.message.refusal
    if ch.finish_reason == "length":
        return "truncated", None, usage, ch.message.content or "", "length"
    return parse(ch.message.content or "", usage)


def call_google(client, cfg, system, user):
    from google.genai import errors, types
    try:
        resp = client.models.generate_content(
            model=cfg["model"],
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_json_schema=JUDGE_SCHEMA,
                temperature=cfg["temperature"],
                max_output_tokens=cfg["max_output_tokens"],
            ),
        )
    except errors.APIError as e:
        return "api_error", None, {}, "", f"{e.code}: {e.message}"

    um = resp.usage_metadata
    cached = (um.cached_content_token_count or 0) if um else 0
    usage = {"input": ((um.prompt_token_count or 0) - cached) if um else 0,
             "output": ((um.candidates_token_count or 0) + (um.thoughts_token_count or 0)) if um else 0,
             "cache_read": cached}
    cand = resp.candidates[0] if resp.candidates else None
    finish = str(cand.finish_reason) if cand else "NO_CANDIDATE"
    if not cand or "SAFETY" in finish or "PROHIBITED" in finish:
        return "refusal", None, usage, "", finish
    if "MAX_TOKENS" in finish:
        return "truncated", None, usage, resp.text or "", finish
    return parse(resp.text or "", usage)


def parse(text, usage):
    try:
        return "ok", json.loads(text), usage, text, ""
    except json.JSONDecodeError as e:
        return "parse_error", None, usage, text, str(e)


def make_client(provider):
    if provider == "anthropic":
        import anthropic
        return anthropic.Anthropic(max_retries=5)
    if provider == "openai":
        import openai
        return openai.OpenAI(max_retries=5)
    if provider == "google":
        from google import genai
        return genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    raise ValueError(provider)


CALLERS = {"anthropic": call_anthropic, "openai": call_openai, "google": call_google}


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_prepare(args):
    run_dir = RUNS_DIR / args.run_id
    if (run_dir / "targets.json").exists():
        sys.exit(f"{run_dir}/targets.json already exists; choose another --run-id")
    run_dir.mkdir(parents=True, exist_ok=True)
    if args.copy_targets_from:
        shutil.copy(RUNS_DIR / args.copy_targets_from / "targets.json", run_dir / "targets.json")
        n = len(json.loads((run_dir / "targets.json").read_text()))
    else:
        keys = sample_keys(None if (args.all or args.place) else args.sample, args.seed,
                           include_duplicates=args.include_duplicates)
        if args.place:
            keys = [k for k in keys if args.place.lower() in k.split("#")[0].lower()]
        (run_dir / "targets.json").write_text(json.dumps(keys, indent=0))
        n = len(keys)
    print(f"{n} targets → {run_dir/'targets.json'}")


def write_meta(run_dir, judges, system):
    import importlib.metadata as md
    meta_path = run_dir / "run_meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {"sessions": []}
    h = prompt_hash(system)
    if meta.get("prompt_hash") not in (None, h):
        sys.exit(f"prompt changed since this run started ({meta['prompt_hash']} → {h}); "
                 "start a new --run-id so results stay comparable")
    cfg = load_config()["judges"]
    meta.update({"prompt_version": PROMPT_VERSION, "prompt_hash": h, "max_lines": MAX_LINES})
    for j in judges:
        if j in meta.get("judges", {}) and meta["judges"][j] != cfg[j]:
            sys.exit(f"judge '{j}' settings changed since this run started "
                     f"({meta['judges'][j]} → {cfg[j]}); start a new --run-id")
    meta.setdefault("judges", {}).update({j: cfg[j] for j in judges})
    meta["sessions"].append({
        "started": now(), "judges": judges,
        "sdk": {p: md.version(p) for p in ("anthropic", "openai", "google-genai")},
    })
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    (run_dir / "system_prompt.txt").write_text(system)


def done_keys(path):
    if not path.exists():
        return set()
    out = set()
    for line in path.read_text().splitlines():
        r = json.loads(line)
        if r["status"] in ("ok", "skipped_large", "refusal"):
            out.add(r["key"])
    return out


def cmd_run(args):
    load_env()
    run_dir = RUNS_DIR / args.run_id
    targets = json.loads((run_dir / "targets.json").read_text())
    if args.limit:
        targets = targets[: args.limit]
    judges = args.judges.split(",")
    cfg_all = load_config()["judges"]
    system = build_system_prompt()
    write_meta(run_dir, judges, system)

    def run_one_judge(judge):
        cfg = cfg_all[judge]
        out = run_dir / f"{judge}.jsonl"
        todo = [k for k in targets if k not in done_keys(out)]
        print(f"[{judge}] {cfg['model']}: {len(todo)} to do ({len(targets) - len(todo)} done)")
        client = make_client(cfg["provider"])
        caller = CALLERS[cfg["provider"]]
        lock = threading.Lock()
        counts = {}

        def work(key):
            rec = load_record(key)
            row = {"key": key, "edcs_id": rec.get("edcs_id"), "judge": judge,
                   "model": cfg["model"], "timestamp": now()}
            lines, _, _ = flatten(rec)
            if len(lines) > MAX_LINES:
                row.update(status="skipped_large", result=None, usage={}, latency_s=0,
                           error=f"{len(lines)} lines > {MAX_LINES}")
            else:
                t0 = time.time()
                status, parsed, usage, raw, err = caller(client, cfg, system, build_user_message(rec))
                row.update(status=status, usage=usage, latency_s=round(time.time() - t0, 1),
                           error=err, result=check_paths(parsed, rec) if parsed else None)
                if status != "ok":
                    row["raw_text"] = raw[:4000]
            with lock:
                with open(out, "a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                counts[row["status"]] = counts.get(row["status"], 0) + 1
            return row["status"]

        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(work, k) for k in todo]
            for i, f in enumerate(as_completed(futs), 1):
                f.result()
                if i % 10 == 0 or i == len(futs):
                    print(f"[{judge}] {i}/{len(futs)} {counts}")
        return judge, counts

    with ThreadPoolExecutor(max_workers=len(judges)) as ex:
        for judge, counts in ex.map(run_one_judge, judges):
            print(f"[{judge}] finished: {counts}")


def cmd_estimate(args):
    load_env()
    import anthropic
    run_dir = RUNS_DIR / args.run_id
    targets = json.loads((run_dir / "targets.json").read_text())
    system = build_system_prompt()
    client = anthropic.Anthropic()
    model = load_config()["judges"]["claude"]["model"]
    sys_tokens = client.messages.count_tokens(
        model=model, system=system, messages=[{"role": "user", "content": "x"}]).input_tokens
    sample = targets[: args.n]
    user_tokens, skipped = [], 0
    for k in sample:
        rec = load_record(k)
        if len(flatten(rec)[0]) > MAX_LINES:
            skipped += 1
            continue
        user_tokens.append(client.messages.count_tokens(
            model=model, messages=[{"role": "user", "content": build_user_message(rec)}]).input_tokens)
    avg = sum(user_tokens) / max(len(user_tokens), 1)
    print(f"system prompt        : {sys_tokens:,} tokens (cacheable)")
    print(f"user message (avg)   : {avg:,.0f} tokens over {len(user_tokens)} samples "
          f"(max {max(user_tokens, default=0):,}; {skipped} over {MAX_LINES} lines)")
    print(f"targets              : {len(targets):,}")
    print(f"total input (no cache): {(sys_tokens + avg) * len(targets) / 1e6:,.1f}M tokens per judge")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare")
    p.add_argument("--run-id", required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--sample", type=int)
    g.add_argument("--all", action="store_true")
    g.add_argument("--copy-targets-from")
    g.add_argument("--place", help="every record whose file path contains this text (e.g. Uthina)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--include-duplicates", action="store_true",
                   help="judge every copy of an EDCS-ID that appears in several place files")
    p.set_defaults(func=cmd_prepare)

    p = sub.add_parser("estimate")
    p.add_argument("--run-id", required=True)
    p.add_argument("--n", type=int, default=20, help="number of targets to count")
    p.set_defaults(func=cmd_estimate)

    p = sub.add_parser("run")
    p.add_argument("--run-id", required=True)
    p.add_argument("--judges", default="claude,gpt,gemini")
    p.add_argument("--workers", type=int, default=4, help="concurrent requests per judge")
    p.add_argument("--limit", type=int, help="only the first N targets")
    p.set_defaults(func=cmd_run)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
