#!/usr/bin/env python3
"""
Build the human-review editor from a judge run's review queue.

Reads  : pipeline/evaluation/llm_judge/runs/<run_id>/review_queue.json
Writes : docs/evaluation/judge_review_<run_id>.html

Inscriptions appear in queue order (format → agree_all → agree_2 → single →
unjudged → audit). For each inscription the reviewer:
  - rules on every field a judge flagged: the extracted value is
    correct / incorrect / undecidable, with the corrected value if incorrect;
  - adds errors no judge flagged ("missed"), so judge recall can be measured;
  - marks the inscription as reviewed.

Audit inscriptions are shown blind: no judge output, only the extraction.

Annotations autosave to the browser (localStorage) and are exported as a
JSON file keyed by record key; loading that file restores them.

Usage
-----
  python build_judge_review_editor.py --run-id pilot01
  python build_judge_review_editor.py --run-id full01 --limit 500 --offset 500
  python build_judge_review_editor.py --run-id full01 --tiers agree_all,agree_2
"""

import argparse
import json
import sys
from pathlib import Path

LLM_JUDGE_DIR = Path(__file__).resolve().parent
EVAL_DIR = LLM_JUDGE_DIR.parent
PROJECT_DIR = EVAL_DIR.parent.parent
sys.path.insert(0, str(EVAL_DIR))
sys.path.insert(0, str(LLM_JUDGE_DIR))
from editor_theme import BASE_CSS, FONT_LINKS  # noqa: E402
from judge_common import RUNS_DIR  # noqa: E402

JUDGE_LABELS = {"claude": "Claude", "gpt": "GPT", "gemini": "Gemini"}

TIER_LABELS = {
    "format": "形式エラー",
    "agree_all": "全judge一致",
    "agree_2": "2judge一致",
    "single": "1judgeのみ",
    "unjudged": "未判定",
    "audit": "監査（ブラインド）",
}
# What the consensus fields agree on (build_review_queue.py consensus_verdict)
VERDICT_LABELS = {"incorrect": "誤り", "mixed": "判定が混在",
                  "omission": "抜け", "uncertain": "判断不能"}

CSS = BASE_CSS + """
main { max-width: 1180px; margin: 0 auto; padding: 18px 20px 80px; }
.tier-badge {
  font-size: 11px; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--border);
  background: var(--muted); color: var(--muted-foreground); white-space: nowrap;
}
.tier-format    { background: var(--incorrect-surface); color: var(--incorrect); border-color: var(--incorrect-border); }
.tier-agree_all { background: var(--incorrect-surface); color: var(--incorrect); border-color: var(--incorrect-border); }
.tier-agree_2   { background: var(--uncertain-surface); color: var(--uncertain); border-color: var(--uncertain-border); }
.tier-audit     { background: var(--accent); color: var(--primary); }
.card-meta { font-size: 12px; color: var(--muted-foreground); margin-left: auto; white-space: nowrap; }
.meta-block { font-family: var(--font-mono); font-size: 12px; color: var(--muted-foreground);
  white-space: pre-wrap; margin: 0 0 12px; }
.section-h { font-size: 12px; font-weight: 600; letter-spacing: .04em; color: var(--muted-foreground);
  margin: 18px 0 8px; text-transform: uppercase; }
.fmt-list { margin: 0 0 8px; padding-left: 18px; font-family: var(--font-mono); font-size: 12px; }
.fmt-list li.err  { color: var(--incorrect); }
.fmt-list li.warn { color: var(--uncertain); }
.flag {
  border: 1px solid var(--border); border-radius: var(--radius); padding: 10px 12px;
  margin-bottom: 10px; background: var(--card);
}
.flag[data-h="extraction_correct"]   { border-left: 3px solid var(--correct); }
.flag[data-h="extraction_incorrect"] { border-left: 3px solid var(--incorrect); }
.flag[data-h="uncertain"]            { border-left: 3px solid var(--uncertain); }
.flag-path { font-family: var(--font-mono); font-size: 13px; font-weight: 600; }
.flag-val  { font-family: var(--font-mono); font-size: 13px; margin: 4px 0 8px;
  padding: 4px 8px; background: var(--muted); border-radius: var(--radius); word-break: break-word; }
.jrow { display: grid; grid-template-columns: 74px 150px 1fr; gap: 8px; font-size: 13px; padding: 4px 0;
  border-top: 1px dashed var(--border); }
.jname { font-weight: 600; }
.jv { font-family: var(--font-mono); font-size: 12px; }
.jv .major { color: var(--incorrect); font-weight: 600; }
.jv .minor { color: var(--muted-foreground); }
.jsug { font-family: var(--font-mono); font-size: 12px; color: var(--primary); margin-top: 2px; }
.jinvalid { color: var(--uncertain); font-size: 11px; }
.h-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-top: 8px; }
.h-row input[type=text] { flex: 1; min-width: 200px; }
.h-row input[type=text], .missed input, .missed select, textarea.h-note {
  font-family: var(--font-mono); font-size: 12px; padding: 5px 8px; border: 1px solid var(--input);
  border-radius: var(--radius); background: var(--background); color: var(--foreground);
}
textarea.h-note { width: 100%; min-height: 48px; box-sizing: border-box; font-family: var(--font-sans); }
.verdict-btn.small { padding: 4px 10px; font-size: 12px; }
details.extraction summary { cursor: pointer; font-size: 13px; color: var(--primary); margin: 14px 0 6px; }
.ext-lines { font-family: var(--font-mono); font-size: 12px; line-height: 1.55; max-height: 420px;
  overflow: auto; background: var(--muted); padding: 8px 10px; border-radius: var(--radius); }
.ext-lines .ctx { color: var(--muted-foreground); }
.ext-lines .hit { background: var(--uncertain-surface); }
.missed { display: grid; grid-template-columns: 1.4fr 120px 1fr 1fr 28px; gap: 6px; margin-bottom: 6px; }
.btn-mini { font-size: 12px; padding: 4px 10px; border: 1px solid var(--border); border-radius: var(--radius);
  background: var(--card); color: var(--foreground); cursor: pointer; }
.done-row { display: flex; align-items: center; gap: 10px; margin-top: 16px; padding-top: 12px;
  border-top: 1px solid var(--border); }
.jnote { font-size: 13px; margin: 4px 0; }
"""

JS = r"""
const RUN_ID = __RUN_ID__;
const JUDGES = __JUDGES__;
const JUDGE_LABELS = __JUDGE_LABELS__;
const TIER_LABELS = __TIER_LABELS__;
const VERDICT_LABELS = __VERDICT_LABELS__;
const DATA = __DATA__;
const STORE_KEY = 'judge_review:' + RUN_ID;

const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

// ── State ─────────────────────────────────────────────────────────────────
function emptyHuman() { return {fields: {}, missed: [], note: '', done: false, reviewed_at: null}; }
DATA.forEach(d => { d.human = emptyHuman(); });

function persist() {
  const out = {};
  DATA.forEach(d => { if (isTouched(d)) out[d.key] = d.human; });
  try { localStorage.setItem(STORE_KEY, JSON.stringify(out)); } catch (e) { /* quota */ }
}
function restore(map) {
  let n = 0;
  DATA.forEach(d => { if (map[d.key]) { d.human = Object.assign(emptyHuman(), map[d.key]); n++; } });
  return n;
}
function isTouched(d) {
  const h = d.human;
  return h.done || h.note || h.missed.length || Object.keys(h.fields).length;
}

// ── Rendering ─────────────────────────────────────────────────────────────
function headerHTML(d, i) {
  const nf = d.flagged.length;
  const badge = d.human.done ? ['vb-correct', '確認済み'] : (isTouched(d) ? ['vb-uncertain', '作業中'] : ['vb-none', '未確認']);
  const meta = d.audit ? '' : (nf ? `${nf} 項目に指摘` : '') + (d.format_errors.length ? ` / 形式エラー ${d.format_errors.length}` : '');
  return `<span class="card-idx">${d.rank}</span>
    <span class="edcs-id">${esc(d.edcs_id)}</span>
    <span class="tier-badge tier-${d.tier}">${esc(TIER_LABELS[d.tier] || d.tier)}${d.consensus_verdict ? '・' + esc(VERDICT_LABELS[d.consensus_verdict] || d.consensus_verdict) : ''}</span>
    <span class="card-meta">${esc(meta)}</span>
    <span class="verdict-badge ${badge[0]}">${badge[1]}</span>
    <span class="chevron">▼</span>`;
}

function judgeRows(f) {
  return JUDGES.map(j => {
    const x = f.judges[j];
    if (!x) return `<div class="jrow"><span class="jname">${JUDGE_LABELS[j]}</span><span class="jv minor">指摘なし</span><span></span></div>`;
    return `<div class="jrow"><span class="jname">${JUDGE_LABELS[j]}</span>
      <span class="jv">${esc(x.verdict)} · <span class="${x.severity}">${esc(x.severity)}</span>
        ${x.path_valid ? '' : '<div class="jinvalid">path が抽出結果に存在しない</div>'}</span>
      <span>${esc(x.reason)}${x.suggested_value ? `<div class="jsug">→ ${esc(x.suggested_value)}</div>` : ''}</span></div>`;
  }).join('');
}

function flagHTML(d, i, f, k) {
  const h = d.human.fields[f.path] || {};
  const btn = (v, label, cls) =>
    `<button class="verdict-btn small ${h.verdict === v ? 'active-' + cls : ''}"
       onclick="setField(${i},${k},'${v}')">${label}</button>`;
  return `<div class="flag" data-h="${esc(h.verdict || '')}">
    <div class="flag-path">${esc(f.path)}</div>
    <div class="flag-val">${f.judged_value == null ? '<i>（抽出結果に該当フィールドなし）</i>' : esc(f.judged_value)}</div>
    ${judgeRows(f)}
    <div class="h-row">
      ${btn('extraction_correct', '✓ 抽出値は正しい', 'correct')}
      ${btn('extraction_incorrect', '✗ 抽出値は誤り', 'incorrect')}
      ${btn('uncertain', '? 判断保留', 'uncertain')}
      <input type="text" placeholder="正しい値（誤りの場合）" value="${esc(h.corrected_value || '')}"
        oninput="setFieldText(${i},${k},'corrected_value',this.value)">
      <input type="text" placeholder="メモ" value="${esc(h.note || '')}"
        oninput="setFieldText(${i},${k},'note',this.value)">
    </div></div>`;
}

function missedHTML(d, i) {
  const rows = d.human.missed.map((m, k) => `<div class="missed">
      <input type="text" list="paths-${i}" placeholder="path（例 persons[0].gender）" value="${esc(m.path)}"
        oninput="setMissed(${i},${k},'path',this.value)">
      <select onchange="setMissed(${i},${k},'kind',this.value)">
        <option value="incorrect" ${m.kind === 'incorrect' ? 'selected' : ''}>値が誤り</option>
        <option value="omission" ${m.kind === 'omission' ? 'selected' : ''}>抜け</option>
      </select>
      <input type="text" placeholder="正しい値" value="${esc(m.corrected_value)}"
        oninput="setMissed(${i},${k},'corrected_value',this.value)">
      <input type="text" placeholder="メモ" value="${esc(m.note)}"
        oninput="setMissed(${i},${k},'note',this.value)">
      <button class="btn-mini" title="削除" onclick="delMissed(${i},${k})">×</button></div>`).join('');
  const opts = d.extraction.map(l => `<option value="${esc(l.split(' = ')[0])}">`).join('');
  return `${rows}<datalist id="paths-${i}">${opts}</datalist>
    <button class="btn-mini" onclick="addMissed(${i})">＋ 指摘されていない誤り・抜けを追加</button>`;
}

function bodyHTML(d, i) {
  const flaggedPaths = new Set(d.flagged.map(f => f.path));
  const ext = d.extraction.map(l => {
    const p = l.split(' = ')[0];
    const cls = l.endsWith('(context)') ? 'ctx' : (flaggedPaths.has(p) ? 'hit' : '');
    return `<div class="${cls}">${esc(l)}</div>`;
  }).join('');
  const fmt = d.format_errors.map(e => `<li class="err">${esc(e)}</li>`).join('')
            + d.format_warnings.map(e => `<li class="warn">${esc(e)}</li>`).join('');
  const notes = Object.entries(d.judge_notes || {})
    .map(([j, n]) => `<div class="jnote"><b>${JUDGE_LABELS[j]}:</b> ${esc(n)}</div>`).join('');
  const status = d.audit ? '' : JUDGES.map(j => `${JUDGE_LABELS[j]}: ${esc(d.judge_status[j])}${d.judge_overall[j] ? ' / ' + esc(d.judge_overall[j]) : ''}`).join('　');

  return `
    <div class="meta-block">${esc(d.metadata)}</div>
    <div class="insc-label">原文（抽出時の入力）</div>
    <pre class="insc-text">${esc(d.inscription) || '（テキストなし）'}</pre>
    ${fmt ? `<div class="section-h">形式チェック</div><ul class="fmt-list">${fmt}</ul>` : ''}
    ${d.audit ? `<div class="section-h">監査対象</div>
      <div class="jnote">judge の指摘はありません。判定結果は表示していません。抽出結果全体を確認し、誤りや抜けがあれば下に追加してください。</div>`
      : `<div class="section-h">judge の判定</div><div class="jnote">${status}</div>${notes}
         ${d.flagged.length ? '' : '<div class="jnote">フィールド単位の指摘はありません。</div>'}`}
    ${d.flagged.map((f, k) => flagHTML(d, i, f, k)).join('')}
    <details class="extraction" ${d.audit || !d.flagged.length ? 'open' : ''}>
      <summary>抽出結果全体（${d.extraction.length} 行、黄色は指摘箇所）</summary>
      <div class="ext-lines">${ext}</div></details>
    <div class="section-h">指摘されていない誤り・抜け</div>
    <div id="missed-${i}">${missedHTML(d, i)}</div>
    <div class="section-h">碑文全体のメモ</div>
    <textarea class="h-note" oninput="setNote(${i},this.value)">${esc(d.human.note)}</textarea>
    <div class="done-row">
      <button class="verdict-btn ${d.human.done ? 'active-correct' : ''}" onclick="toggleDone(${i})">
        ${d.human.done ? '✓ 確認済み（クリックで取り消し）' : 'この碑文を確認済みにする'}</button>
      <span class="jnote" id="done-msg-${i}"></span>
    </div>`;
}

function cardEl(i) { return document.getElementById('card-' + i); }

function rerender(i, keepOpen = true) {
  const d = DATA[i], card = cardEl(i);
  const head = card.querySelector('.card-header'), body = card.querySelector('.card-body');
  head.innerHTML = headerHTML(d, i);
  card.dataset.verdict = d.human.done ? 'correct' : '';
  if (keepOpen && body.classList.contains('open')) body.innerHTML = bodyHTML(d, i);
}

function toggle(i) {
  const card = cardEl(i);
  const head = card.querySelector('.card-header'), body = card.querySelector('.card-body');
  const opening = !body.classList.contains('open');
  if (opening) body.innerHTML = bodyHTML(DATA[i], i);
  head.classList.toggle('open', opening);
  body.classList.toggle('open', opening);
}

// ── Mutations ─────────────────────────────────────────────────────────────
function touch(i) { DATA[i].human.reviewed_at = new Date().toISOString(); persist(); updateProgress(); }

function setField(i, k, v) {
  const path = DATA[i].flagged[k].path, h = DATA[i].human.fields;
  h[path] = Object.assign({corrected_value: '', note: ''}, h[path], {verdict: h[path]?.verdict === v ? null : v});
  touch(i); rerender(i);
}
function setFieldText(i, k, field, val) {
  const path = DATA[i].flagged[k].path, h = DATA[i].human.fields;
  h[path] = Object.assign({verdict: null, corrected_value: '', note: ''}, h[path], {[field]: val});
  touch(i); rerender(i, false);
}
function addMissed(i) {
  DATA[i].human.missed.push({path: '', kind: 'incorrect', corrected_value: '', note: ''});
  touch(i); document.getElementById('missed-' + i).innerHTML = missedHTML(DATA[i], i);
}
function setMissed(i, k, field, val) { DATA[i].human.missed[k][field] = val; touch(i); rerender(i, false); }
function delMissed(i, k) {
  DATA[i].human.missed.splice(k, 1);
  touch(i); document.getElementById('missed-' + i).innerHTML = missedHTML(DATA[i], i);
}
function setNote(i, val) { DATA[i].human.note = val; touch(i); rerender(i, false); }
function toggleDone(i) {
  const d = DATA[i];
  if (!d.human.done) {
    const pending = d.flagged.filter(f => !(d.human.fields[f.path] || {}).verdict).length;
    if (pending && !confirm(`判定していない指摘が ${pending} 件あります。確認済みにしますか？`)) return;
  }
  d.human.done = !d.human.done;
  touch(i); rerender(i);
  if (d.human.done) {             // move on to the next unreviewed card
    const body = cardEl(i).querySelector('.card-body');
    body.classList.remove('open'); cardEl(i).querySelector('.card-header').classList.remove('open');
    const next = DATA.findIndex((x, j) => j > i && !x.human.done && cardEl(j).style.display !== 'none');
    if (next >= 0) { toggle(next); cardEl(next).scrollIntoView({behavior: 'smooth', block: 'start'}); }
  }
}

// ── Progress / filters ────────────────────────────────────────────────────
function updateProgress() {
  const done = DATA.filter(d => d.human.done).length;
  const pct = DATA.length ? (done / DATA.length * 100).toFixed(0) : 0;
  document.getElementById('prog-bar').style.width = pct + '%';
  document.getElementById('prog-label').textContent = `${done} / ${DATA.length} 件 確認済み (${pct}%)`;
}
function applyFilters() {
  const q = document.getElementById('search').value.trim().toLowerCase();
  const tier = document.getElementById('tier-filter').value;
  const st = document.getElementById('status-filter').value;
  let vis = 0;
  DATA.forEach((d, i) => {
    let show = true;
    if (tier && d.tier !== tier) show = false;
    if (st === 'todo' && d.human.done) show = false;
    if (st === 'done' && !d.human.done) show = false;
    if (show && q) {
      const hay = (d.edcs_id + ' ' + d.inscription + ' ' + d.flagged.map(f => f.path).join(' ')).toLowerCase();
      if (!hay.includes(q)) show = false;
    }
    cardEl(i).style.display = show ? '' : 'none';
    if (show) vis++;
  });
  document.getElementById('vis-count').textContent = vis + ' 件表示中';
}

// ── Import / export ───────────────────────────────────────────────────────
function downloadJSON() {
  const annotations = DATA.filter(isTouched).map(d => ({
    key: d.key, edcs_id: d.edcs_id, tier: d.tier, audit: d.audit,
    flagged_paths: d.flagged.map(f => f.path), human: d.human,
  }));
  const blob = new Blob([JSON.stringify({run_id: RUN_ID, exported_at: new Date().toISOString(),
    annotations}, null, 2)], {type: 'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `judge_review_${RUN_ID}_annotations.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}
function loadJSON() {
  const input = document.createElement('input');
  input.type = 'file'; input.accept = '.json';
  input.onchange = e => {
    const file = e.target.files[0]; if (!file) return;
    file.text().then(t => {
      try {
        const obj = JSON.parse(t);
        if (obj.run_id && obj.run_id !== RUN_ID &&
            !confirm(`別の run (${obj.run_id}) の結果です。読み込みますか？`)) return;
        const map = {}; (obj.annotations || []).forEach(a => { map[a.key] = a.human; });
        const n = restore(map);
        DATA.forEach((d, i) => rerender(i)); persist(); updateProgress(); applyFilters();
        alert(`読み込み完了：${n} 件`);
      } catch (err) { alert('JSONの読み込みに失敗しました: ' + err.message); }
    });
  };
  input.click();
}

document.addEventListener('DOMContentLoaded', () => {
  try { restore(JSON.parse(localStorage.getItem(STORE_KEY) || '{}')); } catch (e) {}
  document.getElementById('cards').innerHTML = DATA.map((d, i) =>
    `<div class="card" id="card-${i}" data-idx="${i}">
       <div class="card-header" onclick="toggle(${i})">${headerHTML(d, i)}</div>
       <div class="card-body"></div></div>`).join('');
  DATA.forEach((d, i) => { cardEl(i).dataset.verdict = d.human.done ? 'correct' : ''; });
  updateProgress(); applyFilters();
  document.getElementById('search').addEventListener('input', applyFilters);
  document.getElementById('tier-filter').addEventListener('change', applyFilters);
  document.getElementById('status-filter').addEventListener('change', applyFilters);
});
"""


def build_html(run_id, judges, items, summary):
    def js_literal(obj):
        return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")

    js = (JS.replace("__RUN_ID__", js_literal(run_id))
            .replace("__JUDGES__", js_literal(judges))
            .replace("__JUDGE_LABELS__", js_literal({j: JUDGE_LABELS.get(j, j) for j in judges}))
            .replace("__TIER_LABELS__", js_literal(TIER_LABELS))
            .replace("__VERDICT_LABELS__", js_literal(VERDICT_LABELS))
            .replace("__DATA__", js_literal(items)))
    present = [t for t in TIER_LABELS if any(it["tier"] == t for it in items)]
    tier_opts = "".join(f'<option value="{t}">{TIER_LABELS[t]}</option>' for t in present)
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LLM-as-a-Judge 人手確認 — {run_id}</title>
{FONT_LINKS}
<style>{CSS}</style>
</head>
<body>
<div class="sticky-top">
  <header>
    <h1><span class="eyebrow">Review Editor · run {run_id} · {", ".join(JUDGE_LABELS.get(j, j) for j in judges)}</span>LLM-as-a-Judge 人手確認</h1>
    <div class="header-btns">
      <button class="btn btn-load" onclick="loadJSON()">保存済みJSONを読み込む</button>
      <button class="btn btn-dl" onclick="downloadJSON()">アノテーション結果をダウンロード</button>
    </div>
  </header>
  <div class="filterbar">
    <label>検索 <input type="text" id="search" placeholder="EDCS ID・原文・path…"></label>
    <label>区分 <select id="tier-filter"><option value="">すべて</option>{tier_opts}</select></label>
    <label>状態 <select id="status-filter"><option value="">すべて</option>
      <option value="todo">未確認</option><option value="done">確認済み</option></select></label>
    <span id="vis-count"></span>
  </div>
  <div class="progress-wrap">
    <div class="progress-bar-outer"><div class="progress-bar-inner" id="prog-bar" style="width:0%"></div></div>
    <span class="progress-label" id="prog-label"></span>
  </div>
</div>
<main id="cards"></main>
<script>{js}</script>
</body>
</html>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--tiers", default=None, help="comma-separated tiers to include (default: all)")
    ap.add_argument("--limit", type=int, default=500, help="inscriptions per editor file")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    q = json.loads((RUNS_DIR / args.run_id / "review_queue.json").read_text())
    items = q["items"]
    if args.tiers:
        keep = set(args.tiers.split(","))
        items = [it for it in items if it["tier"] in keep]
    items = items[args.offset: args.offset + args.limit]

    suffix = f"_{args.offset + 1}-{args.offset + len(items)}" if args.offset or len(q["items"]) > args.limit else ""
    out = Path(args.out) if args.out else (
        PROJECT_DIR / "docs" / "evaluation" / f"judge_review_{args.run_id}{suffix}.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(args.run_id, q["summary"]["judges"], items, q["summary"]), encoding="utf-8")
    print(f"{len(items)} inscriptions → {out} ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
