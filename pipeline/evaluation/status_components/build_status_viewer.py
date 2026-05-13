#!/usr/bin/env python3
"""
Build a standalone HTML viewer for the social_status evaluation results.

Reads:
  ../name_components/name_eval_result_claude.json  (aligned person pairs)
  status_mapping.json                              (normalization mapping)
  ../name_components/edh_linked_data/edh_inscriptions.csv  (EDH texts)
  pipeline/provenance/career_graphs/claude/        (EDCS texts)

Output:
  status_viewer.html
"""

import json
import csv
from pathlib import Path
from html import escape
from collections import defaultdict

DIR        = Path(__file__).resolve().parent
PIPELINE   = DIR.parent.parent
PAIRS_JSON = DIR.parent / 'name_components' / 'name_eval_result_claude.json'
MAPPING    = DIR / 'status_mapping.json'
EDH_CSV    = DIR.parent / 'name_components' / 'edh_linked_data' / 'edh_inscriptions.csv'
CG_DIR     = PIPELINE / 'provenance' / 'career_graphs' / 'claude'
HTML_OUT   = PIPELINE.parent / 'docs' / 'evaluation' / 'status_viewer.html'


# ── normalization ─────────────────────────────────────────────────────────────

def build_lookup(mapping: dict) -> dict[str, str]:
    lookup = {}
    for canonical, aliases in mapping.items():
        if canonical.startswith('_'):
            continue
        lookup[canonical] = canonical
        for alias in aliases:
            lookup[alias.lower()] = canonical
    return lookup

def normalize(value: str, lookup: dict) -> str | None:
    v = (value or '').strip().lower()
    return lookup.get(v) or lookup.get(v.replace('_', '-')) or lookup.get(v.replace('-', '_'))


# ── load texts ────────────────────────────────────────────────────────────────

def load_edh_texts() -> dict[str, dict]:
    texts = {}
    with open(EDH_CSV, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            hd = row.get('hd_number', '')
            if hd:
                texts[hd] = {
                    'edition_text':    row.get('edition_text', ''),
                    'diplomatic_text': row.get('diplomatic_text', ''),
                }
    return texts

def load_cg_texts() -> dict[str, str]:
    texts = {}
    for json_path in sorted(CG_DIR.rglob('*.json')):
        try:
            for rec in json.loads(json_path.read_text(encoding='utf-8')):
                eid = rec.get('edcs_id', '')
                if not eid:
                    continue
                orig = rec.get('original_data', {}) or {}
                text = orig.get('inscription_conservative_cleaning') or orig.get('inscription') or ''
                if text and eid not in texts:
                    texts[eid] = text
        except Exception:
            continue
    return texts


# ── status classification per pair ────────────────────────────────────────────

def classify_pair(pair: dict, lookup: dict) -> str:
    """Returns 'match', 'fp', 'fn', 'missing', or 'skip'."""
    if not pair.get('aligned'):
        return 'skip'
    edh_norm = normalize(pair.get('edh_status', ''), lookup)
    cg_norm  = normalize(pair.get('cg_status',  ''), lookup)
    if edh_norm is None and cg_norm is None:
        return 'missing'
    if edh_norm is None:
        return 'skip'
    if cg_norm == edh_norm:
        return 'match'
    if cg_norm is None:
        return 'fn'
    return 'fp'


# ── HTML rendering ────────────────────────────────────────────────────────────

def render_pair_row(pair: dict, lookup: dict, idx: int) -> str:
    cls = classify_pair(pair, lookup)
    if cls == 'skip' or cls == 'missing':
        return ''

    edh_raw  = pair.get('edh_status', '') or ''
    cg_raw   = pair.get('cg_status',  '') or ''
    edh_norm = normalize(edh_raw, lookup) or '—'
    cg_norm  = normalize(cg_raw,  lookup) or '—'
    edh_name = escape(pair.get('edh_name', '') or '—')
    cg_name  = escape(pair.get('cg_name',  '') or '—')

    if cls == 'match':
        row_cls = 'status-match'
        badge   = '<span class="badge match-badge">match</span>'
    elif cls == 'fp':
        row_cls = 'status-fp'
        badge   = '<span class="badge fp-badge">FP</span>'
    else:  # fn
        row_cls = 'status-fn'
        badge   = '<span class="badge fn-badge">FN</span>'

    return f'''
        <tr class="{row_cls}">
          <td class="person-idx">{idx}</td>
          <td>{edh_name}</td>
          <td>{cg_name}</td>
          <td><span class="status-val">{escape(edh_raw)}</span><br><span class="norm-val">→ {escape(edh_norm)}</span></td>
          <td><span class="status-val">{escape(cg_raw)}</span><br><span class="norm-val">→ {escape(cg_norm)}</span></td>
          <td>{badge}</td>
        </tr>'''


def result_status_pairs(result: dict, lookup: dict) -> list[tuple[int, dict, str]]:
    """Returns (idx, pair, cls) for pairs that are not skip/missing."""
    out = []
    for i, p in enumerate(result.get('pairs', []), 1):
        cls = classify_pair(p, lookup)
        if cls not in ('skip', 'missing'):
            out.append((i, p, cls))
    return out


def render_result(result: dict, lookup: dict, edh_texts: dict, cg_texts: dict) -> str | None:
    hd   = result['hd_number']
    eids = result.get('edcs_ids', [result.get('edcs_id', '')])
    pairs = result_status_pairs(result, lookup)
    if not pairs:
        return None

    has_error = any(cls in ('fp', 'fn') for _, _, cls in pairs)

    cg_text  = next((cg_texts.get(e, '') for e in eids if cg_texts.get(e)), '')
    edh_t    = edh_texts.get(hd, {})
    ed_text  = edh_t.get('edition_text', '')

    rows_html = ''
    for idx, pair, _ in pairs:
        rows_html += render_pair_row(pair, lookup, idx)

    err_cls  = 'has-error' if has_error else 'no-error'
    err_badge = '<span class="badge err-badge">ERRORS</span>' if has_error else ''

    return f'''
  <div class="inscription {err_cls}" id="{hd}" data-hd="{hd}" data-haserr="{str(has_error).lower()}">
    <div class="insc-header" onclick="toggleCard(this)">
      <span class="hd-num">{hd}</span>
      <span class="edcs-num">{escape(", ".join(eids))}</span>
      {err_badge}
      <span class="toggle-arrow">▼</span>
    </div>
    <div class="insc-body">
      <div class="text-columns">
        <div class="text-col">
          <div class="text-col-label">EDCS（LLM入力）</div>
          <div class="inscription-text">{escape(cg_text) if cg_text else '<span class="empty">（テキストなし）</span>'}</div>
        </div>
        <div class="text-col">
          <div class="text-col-label">EDH edition text</div>
          <div class="inscription-text">{escape(ed_text) if ed_text else '<span class="empty">（テキストなし）</span>'}</div>
        </div>
      </div>
      <table class="status-table">
        <thead>
          <tr>
            <th>#</th><th>EDH name</th><th>CG name</th>
            <th>EDH status（正規化）</th><th>CG status（正規化）</th><th></th>
          </tr>
        </thead>
        <tbody>{rows_html}
        </tbody>
      </table>
    </div>
  </div>'''


# ── summary ───────────────────────────────────────────────────────────────────

def build_summary(results: list[dict], lookup: dict) -> dict:
    tp = defaultdict(int)
    fp = defaultdict(int)
    fn = defaultdict(int)
    for r in results:
        for p in r.get('pairs', []):
            cls      = classify_pair(p, lookup)
            edh_norm = normalize(p.get('edh_status', ''), lookup)
            cg_norm  = normalize(p.get('cg_status',  ''), lookup)
            if cls == 'match':
                tp[edh_norm] += 1
            elif cls == 'fp':
                fn[edh_norm] += 1
                fp[cg_norm]  += 1
            elif cls == 'fn':
                fn[edh_norm] += 1
    return {'tp': dict(tp), 'fp': dict(fp), 'fn': dict(fn)}


def prf(t, fp_, fn_):
    p = t / (t + fp_) if (t + fp_) else 0
    r = t / (t + fn_) if (t + fn_) else 0
    f = 2*p*r / (p+r) if (p+r) else 0
    return p, r, f


CSS = '''
:root { --match:#d4edda; --fp:#f8d7da; --fn:#fff3cd; --miss:#f8f9fa; --border:#dee2e6; }
* { box-sizing:border-box; margin:0; padding:0; }
body { font-family:'Segoe UI',system-ui,sans-serif; font-size:14px; background:#f0f2f5; color:#212529; }
header { background:#343a40; color:#fff; padding:16px 24px; position:sticky; top:0; z-index:100; }
header h1 { font-size:1.2rem; }
header .subtitle { font-size:.8rem; opacity:.7; margin-top:4px; }
.controls { background:#fff; padding:12px 24px; border-bottom:1px solid var(--border);
            display:flex; flex-wrap:wrap; gap:12px; align-items:center; position:sticky; top:56px; z-index:99; }
.controls label { font-size:13px; }
.controls input, .controls select { padding:4px 8px; border:1px solid var(--border); border-radius:4px; font-size:13px; }
#searchBox { width:180px; }
.count-info { margin-left:auto; font-size:12px; color:#6c757d; }
main { padding:16px 24px; max-width:1200px; margin:0 auto; }

.summary-box { background:#fff; border:1px solid var(--border); border-radius:8px; padding:16px; margin-bottom:16px; }
.summary-box h2 { font-size:1rem; margin-bottom:10px; }
.summary-table { width:100%; border-collapse:collapse; font-size:13px; }
.summary-table th { background:#e9ecef; padding:6px 10px; text-align:left; }
.summary-table td { padding:6px 10px; border-bottom:1px solid #f0f0f0; }
.summary-table tr.avg-row td { font-weight:700; background:#f8f9fa; border-top:1px solid #adb5bd; }

.inscription { background:#fff; border:1px solid var(--border); border-radius:8px; margin-bottom:12px; overflow:hidden; }
.inscription.has-error { border-left:4px solid #dc3545; }
.inscription.no-error  { border-left:4px solid #28a745; }
.insc-header { padding:10px 16px; cursor:pointer; display:flex; align-items:center; gap:10px;
               background:#f8f9fa; border-bottom:1px solid var(--border); user-select:none; }
.insc-header:hover { background:#e9ecef; }
.hd-num { font-weight:700; font-size:1rem; min-width:100px; }
.edcs-num { color:#6c757d; font-size:12px; }
.toggle-arrow { margin-left:auto; color:#6c757d; transition:transform .2s; }
.insc-header.open .toggle-arrow { transform:rotate(180deg); }
.insc-body { display:none; padding:16px; }
.insc-body.open { display:block; }

.text-columns { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:16px; }
.text-col-label { font-size:11px; font-weight:600; color:#6c757d; margin-bottom:4px; }
.inscription-text { background:#fafafa; border:1px solid #e0e0e0; border-radius:4px;
                    padding:10px 14px; font-family:monospace; font-size:13px;
                    white-space:pre-wrap; word-break:break-word; max-height:120px; overflow-y:auto; color:#495057; }

.status-table { width:100%; border-collapse:collapse; font-size:13px; }
.status-table th { background:#e9ecef; padding:6px 10px; text-align:left; border-bottom:1px solid var(--border); }
.status-table td { padding:6px 10px; border-bottom:1px solid #f0f0f0; vertical-align:top; }
.status-match { background:var(--match); }
.status-fp    { background:var(--fp); }
.status-fn    { background:var(--fn); }
.person-idx { color:#6c757d; font-weight:600; width:30px; }
.status-val { font-weight:600; }
.norm-val { font-size:11px; color:#6c757d; }
.empty { color:#bbb; font-style:italic; }

.badge { font-size:10px; padding:2px 6px; border-radius:10px; font-weight:700; white-space:nowrap; }
.match-badge { background:#d4edda; color:#0a3622; border:1px solid #badbcc; }
.fp-badge    { background:#f8d7da; color:#842029; border:1px solid #f5c2c7; }
.fn-badge    { background:#fff3cd; color:#664d03; border:1px solid #ffecb5; }
.err-badge   { background:#dc3545; color:#fff; }
.hidden { display:none !important; }
'''

JS = '''
function toggleCard(h) {
  h.classList.toggle('open');
  h.nextElementSibling.classList.toggle('open');
}
function applyFilters() {
  const errOnly = document.getElementById('errOnly').checked;
  const search  = document.getElementById('searchBox').value.trim().toLowerCase();
  const cat     = document.getElementById('catFilter').value;
  let vis = 0;
  document.querySelectorAll('.inscription').forEach(card => {
    if (search && !card.dataset.hd.toLowerCase().includes(search)) { card.classList.add('hidden'); return; }
    if (errOnly && card.dataset.haserr !== 'true') { card.classList.add('hidden'); return; }
    if (cat !== 'all') {
      const found = [...card.querySelectorAll('.status-val')].some(el => el.textContent.toLowerCase().includes(cat));
      if (!found) { card.classList.add('hidden'); return; }
    }
    card.classList.remove('hidden'); vis++;
  });
  document.getElementById('visCount').textContent = vis + ' 件表示中';
}
function expandAll()  { document.querySelectorAll('.insc-header:not(.hidden)').forEach(h => { if (!h.classList.contains('open')) toggleCard(h); }); }
function collapseAll(){ document.querySelectorAll('.insc-header.open').forEach(h => toggleCard(h)); }
document.addEventListener('DOMContentLoaded', () => {
  ['errOnly','searchBox','catFilter'].forEach(id => document.getElementById(id).addEventListener('change', applyFilters));
  document.getElementById('searchBox').addEventListener('input', applyFilters);
  applyFilters();
});
'''


def build_html(results: list[dict], lookup: dict, mapping: dict,
               edh_texts: dict, cg_texts: dict) -> str:
    smry = build_summary(results, lookup)
    tp, fp, fn = smry['tp'], smry['fp'], smry['fn']
    categories = sorted(set(list(tp) + list(fp) + list(fn)))

    # summary table rows — per category
    total_tp = total_fp = total_fn = 0
    smry_rows = ''
    cat_prf_list = []
    for cat in categories:
        t, fp_, fn_ = tp.get(cat,0), fp.get(cat,0), fn.get(cat,0)
        total_tp += t; total_fp += fp_; total_fn += fn_
        pr, rc, f1 = prf(t, fp_, fn_)
        cat_prf_list.append((pr, rc, f1, t + fn_))  # (P, R, F1, weight=EDH count)
        smry_rows += f'''
          <tr>
            <td>{escape(cat)}</td>
            <td>{t}</td><td>{fp_}</td><td>{fn_}</td>
            <td>{pr:.1%}</td><td>{rc:.1%}</td><td>{f1:.1%}</td>
          </tr>'''

    smry_rows += '<tr><td colspan="7" style="border-top:2px solid #adb5bd;padding:0"></td></tr>'

    # マイクロ平均
    p_micro, r_micro, f1_micro = prf(total_tp, total_fp, total_fn)
    smry_rows += f'''
          <tr class="avg-row">
            <td>MICRO avg</td>
            <td>{total_tp}</td><td>{total_fp}</td><td>{total_fn}</td>
            <td>{p_micro:.1%}</td><td>{r_micro:.1%}</td><td>{f1_micro:.1%}</td>
          </tr>'''

    # マクロ平均（カテゴリ均等）
    n_cats = len(cat_prf_list)
    p_macro  = sum(x[0] for x in cat_prf_list) / n_cats
    r_macro  = sum(x[1] for x in cat_prf_list) / n_cats
    f1_macro = sum(x[2] for x in cat_prf_list) / n_cats
    smry_rows += f'''
          <tr class="avg-row">
            <td>MACRO avg</td>
            <td colspan="3"></td>
            <td>{p_macro:.1%}</td><td>{r_macro:.1%}</td><td>{f1_macro:.1%}</td>
          </tr>'''

    # 件数加重マクロ平均
    total_w   = sum(x[3] for x in cat_prf_list)
    p_wmacro  = sum(x[3]*x[0] for x in cat_prf_list) / total_w if total_w else 0
    r_wmacro  = sum(x[3]*x[1] for x in cat_prf_list) / total_w if total_w else 0
    f1_wmacro = sum(x[3]*x[2] for x in cat_prf_list) / total_w if total_w else 0
    smry_rows += f'''
          <tr class="avg-row">
            <td>WEIGHTED MACRO avg</td>
            <td colspan="3"></td>
            <td>{p_wmacro:.1%}</td><td>{r_wmacro:.1%}</td><td>{f1_wmacro:.1%}</td>
          </tr>'''

    # category filter options
    cat_opts = '<option value="all">すべて</option>\n'
    cat_opts += '\n'.join(f'<option value="{c}">{escape(c)}</option>' for c in categories)

    # cards
    cards = []
    for r in results:
        html = render_result(r, lookup, edh_texts, cg_texts)
        if html:
            cards.append(html)
    cards_html = '\n'.join(cards)
    total_cards = len(cards)

    return f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EDH vs CG — Social Status Evaluation</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>EDH vs Career Graph — Social Status Evaluation</h1>
  <div class="subtitle">Africa Proconsularis + Numidia &nbsp;|&nbsp; {total_cards} 碑文（status評価あり）</div>
</header>
<div class="controls">
  <label><input type="checkbox" id="errOnly"> エラーのある碑文のみ</label>
  <label>HD番号: <input type="text" id="searchBox" placeholder="HD000379"></label>
  <label>カテゴリ: <select id="catFilter">{cat_opts}</select></label>
  <button onclick="expandAll()">すべて展開</button>
  <button onclick="collapseAll()">すべて折りたたむ</button>
  <span class="count-info" id="visCount">{total_cards} 件表示中</span>
</div>
<main>
  <div class="summary-box">
    <h2>評価サマリー</h2>
    <table class="summary-table">
      <thead><tr><th>Category</th><th>TP</th><th>FP</th><th>FN</th><th>Precision</th><th>Recall</th><th>F1</th></tr></thead>
      <tbody>{smry_rows}</tbody>
    </table>
  </div>
{cards_html}
</main>
<script>{JS}</script>
</body>
</html>'''


def main():
    print('Loading mapping ...')
    mapping = json.loads(MAPPING.read_text(encoding='utf-8'))
    lookup  = build_lookup(mapping)

    print('Loading EDH texts ...')
    edh_texts = load_edh_texts()
    print(f'  {len(edh_texts):,} entries')

    print('Loading CG texts ...')
    cg_texts = load_cg_texts()
    print(f'  {len(cg_texts):,} entries')

    print('Loading evaluation pairs ...')
    data    = json.loads(PAIRS_JSON.read_text(encoding='utf-8'))
    results = data['results']
    print(f'  {len(results)} inscriptions')

    print('Building HTML ...')
    html = build_html(results, lookup, mapping, edh_texts, cg_texts)
    HTML_OUT.write_text(html, encoding='utf-8')
    print(f'Saved → {HTML_OUT}  ({HTML_OUT.stat().st_size/1024:.0f} KB)')


if __name__ == '__main__':
    main()
