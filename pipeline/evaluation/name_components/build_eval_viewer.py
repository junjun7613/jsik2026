#!/usr/bin/env python3
"""
Build a standalone HTML viewer for the name-component evaluation results.

Reads:
  - name_eval_result_claude.json   (evaluation pairs)
  - provenance/career_graphs/claude/**/*.json  (inscription texts)

Output:
  evaluation/eval_viewer.html
"""

import json
import re
from pathlib import Path
from html import escape

EVAL_DIR      = Path(__file__).parent
PIPELINE      = EVAL_DIR.parent.parent
CG_DIR        = PIPELINE / 'provenance' / 'career_graphs' / 'claude'
JSON_IN       = EVAL_DIR / 'name_eval_result_claude.json'
HTML_OUT      = PIPELINE.parent / 'docs' / 'evaluation' / 'eval_viewer.html'
EDH_INSC_CSV  = EVAL_DIR / 'edh_linked_data' / 'edh_inscriptions.csv'


# ── load EDH texts keyed by HD number ─────────────────────────────────────────

def load_edh_texts() -> dict[str, dict[str, str]]:
    """{ hd_number: {edition_text, diplomatic_text} }"""
    import csv
    texts: dict[str, dict[str, str]] = {}
    if not EDH_INSC_CSV.exists():
        return texts
    with open(EDH_INSC_CSV, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            hd = row.get('hd_number', '')
            ed = row.get('edition_text', '')
            di = row.get('diplomatic_text', '')
            if hd and (ed or di):
                texts[hd] = {'edition_text': ed, 'diplomatic_text': di}
    return texts


# ── load inscription texts keyed by EDCS-ID ───────────────────────────────────

def load_inscription_texts() -> dict[str, str]:
    texts: dict[str, str] = {}
    for json_path in sorted(CG_DIR.rglob('*.json')):
        try:
            data = json.loads(json_path.read_text(encoding='utf-8'))
            for rec in data:
                eid = rec.get('edcs_id', '')
                if not eid:
                    continue
                orig = rec.get('original_data', {}) or {}
                text = (orig.get('inscription_conservative_cleaning')
                        or orig.get('inscription') or '')
                if text and eid not in texts:
                    texts[eid] = text
        except Exception:
            continue
    return texts


# ── cell helpers ──────────────────────────────────────────────────────────────

def cell_class(status: str) -> str:
    return {
        'match':    'match',
        'mismatch': 'fp',
        'missing':  'missing',
    }.get(status, 'missing')


def pair_has_error(pair: dict) -> bool:
    for f in ('m_praenomen', 'm_nomen', 'm_cognomen', 'm_gender'):
        if pair.get(f) in ('mismatch',):
            return True
    for f in ('m_praenomen', 'm_nomen', 'm_cognomen', 'm_gender'):
        if pair.get(f) == 'missing':
            edh_key = 'edh_' + f[2:]
            if pair.get(edh_key):
                return True
    return False


def result_has_error(result: dict) -> bool:
    return any(pair_has_error(p) for p in result.get('pairs', []))


# ── per-pair table row (EDH vs CG) ────────────────────────────────────────────

FIELDS = [
    ('praenomen', 'Praenomen'),
    ('nomen',     'Nomen'),
    ('cognomen',  'Cognomen'),
    ('gender',    'Gender'),
]


def render_pair(pair: dict, idx: int) -> str:
    aligned = pair.get('aligned', False)
    overlap = pair.get('name_overlap', 0.0)

    rows_html = ''
    for fkey, flabel in FIELDS:
        edh_val = pair.get(f'edh_{fkey}', '') or ''
        cg_val  = pair.get(f'cg_{fkey}',  '') or ''
        status  = pair.get(f'm_{fkey}',   'missing')

        # Determine display class:
        # FP = mismatch (CG has wrong value)
        # FN = EDH has value but CG is empty → "missing" with edh non-empty
        if status == 'mismatch':
            edh_cls = 'fp'
            cg_cls  = 'fp'
        elif status == 'missing' and edh_val:
            edh_cls = 'fn'
            cg_cls  = 'fn'
        elif status == 'match':
            edh_cls = 'match'
            cg_cls  = 'match'
        else:
            edh_cls = 'missing'
            cg_cls  = 'missing'

        badge = ''
        if status == 'mismatch':
            badge = '<span class="badge fp-badge">FP</span>'
        elif status == 'missing' and edh_val:
            badge = '<span class="badge fn-badge">FN</span>'

        rows_html += f'''
          <tr>
            <td class="field-label">{escape(flabel)}</td>
            <td class="{edh_cls}">{escape(edh_val) or '<span class="empty">—</span>'}</td>
            <td class="{cg_cls}">{escape(cg_val)  or '<span class="empty">—</span>'}</td>
            <td>{badge}</td>
          </tr>'''

    align_badge = (
        f'<span class="badge align-badge">aligned&nbsp;{overlap:.2f}</span>'
        if aligned else
        '<span class="badge noalign-badge">unaligned</span>'
    )
    edh_name = escape(pair.get('edh_name', '') or '—')
    cg_name  = escape(pair.get('cg_name',  '') or '—')

    return f'''
      <div class="pair" data-aligned="{str(aligned).lower()}">
        <div class="pair-header">
          <span class="pair-idx">Person {idx}</span>
          {align_badge}
          <span class="pair-names">EDH: <b>{edh_name}</b> &nbsp;↔&nbsp; CG: <b>{cg_name}</b></span>
        </div>
        <table class="pair-table">
          <thead>
            <tr>
              <th>Field</th><th>EDH (ground truth)</th><th>CG output</th><th></th>
            </tr>
          </thead>
          <tbody>{rows_html}
          </tbody>
        </table>
      </div>'''


def render_result(result: dict, texts: dict[str, str], edh_texts: dict[str, dict]) -> str:
    hd  = result['hd_number']
    eid = result.get('edcs_id', '')
    eids = result.get('edcs_ids', [eid])
    edh_n = result.get('edh_count', '?')
    cg_n  = result.get('cg_count',  '?')
    count_match = result.get('count_match', False)

    # EDCS (CG) inscription text
    insc_text = ''
    for e in eids:
        insc_text = texts.get(e, '')
        if insc_text:
            break

    # EDH inscription texts
    edh_t = edh_texts.get(hd, {})
    edition_text    = edh_t.get('edition_text', '')
    diplomatic_text = edh_t.get('diplomatic_text', '')

    count_cls = 'count-match' if count_match else 'count-mismatch'

    pairs_html = ''
    for i, pair in enumerate(result.get('pairs', []), 1):
        pairs_html += render_pair(pair, i)

    # CG persons not matched to any EDH person
    unmatched_cg = result.get('unmatched_cg', [])
    unmatched_html = ''
    if unmatched_cg:
        rows = ''
        for cp in unmatched_cg:
            name = escape(cp.get('cg_name', '') or '—')
            prae = escape(cp.get('cg_praenomen', '') or '—')
            nom  = escape(cp.get('cg_nomen',     '') or '—')
            cog  = escape(cp.get('cg_cognomen',  '') or '—')
            gen  = escape(cp.get('cg_gender',    '') or '—')
            rows += f'''
            <tr>
              <td>{name}</td>
              <td>{prae}</td><td>{nom}</td><td>{cog}</td><td>{gen}</td>
            </tr>'''
        unmatched_html = f'''
      <div class="unmatched-cg">
        <div class="unmatched-header">
          <span class="badge fp-badge">FP</span>
          CG側のみ（EDHに対応なし）: {len(unmatched_cg)}人
        </div>
        <table class="pair-table">
          <thead>
            <tr><th>CG name</th><th>Praenomen</th><th>Nomen</th><th>Cognomen</th><th>Gender</th></tr>
          </thead>
          <tbody>{rows}
          </tbody>
        </table>
      </div>'''

    has_err = result_has_error(result) or bool(unmatched_cg)
    err_cls = 'has-error' if has_err else 'no-error'

    edcs_str = ', '.join(eids)

    return f'''
  <div class="inscription {err_cls}" id="{hd}" data-hd="{hd}" data-haserr="{str(has_err).lower()}">
    <div class="insc-header" onclick="toggleCard(this)">
      <span class="hd-num">{hd}</span>
      <span class="edcs-num">{escape(edcs_str)}</span>
      <span class="{count_cls}">EDH {edh_n}人 / CG {cg_n}人</span>
      {'<span class="badge err-badge">ERRORS</span>' if has_err else ''}
      <span class="toggle-arrow">▼</span>
    </div>
    <div class="insc-body">
      <div class="text-columns">
        <div class="text-col">
          <div class="text-col-label">EDCS（LLM入力テキスト）</div>
          <div class="inscription-text">{escape(insc_text) if insc_text else '<span class="empty">（テキストなし）</span>'}</div>
        </div>
        <div class="text-col">
          <div class="text-col-label">EDH edition text</div>
          <div class="inscription-text">{escape(edition_text) if edition_text else '<span class="empty">（テキストなし）</span>'}</div>
        </div>
        <div class="text-col">
          <div class="text-col-label">EDH diplomatic text</div>
          <div class="inscription-text">{escape(diplomatic_text) if diplomatic_text else '<span class="empty">（テキストなし）</span>'}</div>
        </div>
      </div>
      <div class="pairs-container">{pairs_html}
{unmatched_html}
      </div>
    </div>
  </div>'''


# ── full HTML ─────────────────────────────────────────────────────────────────

CSS = '''
:root {
  --match: #d4edda;
  --fp:    #f8d7da;
  --fn:    #fff3cd;
  --miss:  #f8f9fa;
  --border: #dee2e6;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', system-ui, sans-serif; font-size: 14px;
       background: #f0f2f5; color: #212529; }
header { background: #343a40; color: #fff; padding: 16px 24px; position: sticky; top:0; z-index:100; }
header h1 { font-size: 1.2rem; }
header .subtitle { font-size: 0.8rem; opacity: 0.7; margin-top: 4px; }

.controls { background: #fff; padding: 12px 24px; border-bottom: 1px solid var(--border);
            display: flex; flex-wrap: wrap; gap: 12px; align-items: center; position: sticky; top: 56px; z-index: 99; }
.controls label { font-size: 13px; }
.controls input, .controls select { padding: 4px 8px; border: 1px solid var(--border); border-radius: 4px; font-size: 13px; }
#searchBox { width: 180px; }
.count-info { margin-left: auto; font-size: 12px; color: #6c757d; }

.legend { display: flex; gap: 16px; padding: 8px 24px; background: #fff; border-bottom: 1px solid var(--border); font-size: 12px; }
.legend-item { display: flex; align-items: center; gap: 5px; }
.legend-swatch { width: 14px; height: 14px; border-radius: 3px; display: inline-block; }

main { padding: 16px 24px; max-width: 1200px; margin: 0 auto; }

.inscription { background: #fff; border: 1px solid var(--border); border-radius: 8px;
               margin-bottom: 12px; overflow: hidden; }
.inscription.has-error { border-left: 4px solid #dc3545; }
.inscription.no-error  { border-left: 4px solid #28a745; }

.insc-header { padding: 10px 16px; cursor: pointer; display: flex; align-items: center; gap: 10px;
               background: #f8f9fa; border-bottom: 1px solid var(--border); user-select: none; }
.insc-header:hover { background: #e9ecef; }
.hd-num { font-weight: 700; font-size: 1rem; color: #343a40; min-width: 100px; }
.edcs-num { color: #6c757d; font-size: 12px; }
.count-match   { color: #28a745; font-size: 12px; font-weight: 600; }
.count-mismatch{ color: #dc3545; font-size: 12px; font-weight: 600; }
.toggle-arrow  { margin-left: auto; color: #6c757d; transition: transform 0.2s; }
.insc-header.open .toggle-arrow { transform: rotate(180deg); }

.insc-body { display: none; padding: 16px; }
.insc-body.open { display: block; }

.text-columns { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; margin-bottom: 16px; }
.text-col-label { font-size: 11px; font-weight: 600; color: #6c757d; margin-bottom: 4px; }
.inscription-text { background: #fafafa; border: 1px solid #e0e0e0; border-radius: 4px;
                    padding: 10px 14px; font-family: monospace; font-size: 13px;
                    white-space: pre-wrap; word-break: break-word;
                    max-height: 150px; overflow-y: auto; color: #495057; }

.pairs-container { display: flex; flex-direction: column; gap: 12px; }

.pair { border: 1px solid #e0e0e0; border-radius: 6px; overflow: hidden; }
.pair-header { background: #f1f3f5; padding: 8px 12px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.pair-idx { font-weight: 700; font-size: 13px; }
.pair-names { font-size: 12px; color: #495057; }

.pair-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.pair-table th { background: #e9ecef; padding: 6px 10px; text-align: left; border-bottom: 1px solid var(--border); }
.pair-table td { padding: 6px 10px; border-bottom: 1px solid #f0f0f0; }
.pair-table tr:last-child td { border-bottom: none; }
.field-label { color: #6c757d; font-weight: 600; width: 100px; }

.match   { background: var(--match); }
.fp      { background: var(--fp); }
.fn      { background: var(--fn); }
.missing { background: var(--miss); color: #aaa; }

.empty { color: #bbb; font-style: italic; }

.unmatched-cg { border: 1px solid #f5c2c7; border-radius: 6px; overflow: hidden; }
.unmatched-header { background: #f8d7da; padding: 8px 12px; font-size: 12px;
                    color: #842029; display: flex; align-items: center; gap: 8px; }
.unmatched-cg .pair-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.unmatched-cg .pair-table th { background: #f5c2c7; padding: 5px 10px; text-align: left;
                                 border-bottom: 1px solid #f5c2c7; }
.unmatched-cg .pair-table td { padding: 5px 10px; border-bottom: 1px solid #fce8e9; background: #fff5f5; }

.badge { font-size: 10px; padding: 2px 6px; border-radius: 10px; font-weight: 700; white-space: nowrap; }
.fp-badge      { background: #f8d7da; color: #842029; border: 1px solid #f5c2c7; }
.fn-badge      { background: #fff3cd; color: #664d03; border: 1px solid #ffecb5; }
.err-badge     { background: #dc3545; color: #fff; }
.align-badge   { background: #d1e7dd; color: #0a3622; border: 1px solid #badbcc; }
.noalign-badge { background: #e2e3e5; color: #41464b; border: 1px solid #d3d6d8; }

.summary-box { background: #fff; border: 1px solid var(--border); border-radius: 8px;
               padding: 16px; margin-bottom: 16px; }
.summary-box h2 { font-size: 1rem; margin-bottom: 10px; }
.summary-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 8px; }
.summary-item { background: #f8f9fa; border-radius: 6px; padding: 8px 12px; }
.summary-label { font-size: 11px; color: #6c757d; }
.summary-value { font-size: 1.2rem; font-weight: 700; color: #343a40; }

.hidden { display: none !important; }
'''

JS = '''
function toggleCard(header) {
  header.classList.toggle('open');
  header.nextElementSibling.classList.toggle('open');
}

function applyFilters() {
  const errOnly  = document.getElementById('errOnly').checked;
  const search   = document.getElementById('searchBox').value.trim().toLowerCase();
  const errField = document.getElementById('errField').value;  // 'all','fp','fn','nomen',...

  let vis = 0;
  document.querySelectorAll('.inscription').forEach(card => {
    const hd      = card.dataset.hd.toLowerCase();
    const hasErr  = card.dataset.haserr === 'true';

    // search filter
    if (search && !hd.includes(search)) { card.classList.add('hidden'); return; }

    // error-only filter
    if (errOnly && !hasErr) { card.classList.add('hidden'); return; }

    // field/type filter
    if (errField !== 'all') {
      const [ftype, ffield] = errField.split(':');
      let found = false;
      card.querySelectorAll('.pair').forEach(pair => {
        // find badge matching ftype
        const badges = pair.querySelectorAll('.badge');
        badges.forEach(b => {
          if (ftype === 'fp' && b.classList.contains('fp-badge')) {
            if (!ffield || b.closest('tr') && b.closest('tr').querySelector('.field-label')
                && b.closest('tr').querySelector('.field-label').textContent.toLowerCase().includes(ffield)) {
              found = true;
            } else if (!ffield) {
              found = true;
            }
          }
          if (ftype === 'fn' && b.classList.contains('fn-badge')) {
            found = true;
          }
        });
      });
      if (!found) { card.classList.add('hidden'); return; }
    }

    card.classList.remove('hidden');
    vis++;
  });
  document.getElementById('visCount').textContent = vis + ' 件表示中';
}

function expandAll() {
  document.querySelectorAll('.insc-header:not(.hidden)').forEach(h => {
    if (!h.classList.contains('open')) toggleCard(h);
  });
}
function collapseAll() {
  document.querySelectorAll('.insc-header.open').forEach(h => toggleCard(h));
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('errOnly').addEventListener('change', applyFilters);
  document.getElementById('searchBox').addEventListener('input', applyFilters);
  document.getElementById('errField').addEventListener('change', applyFilters);
  applyFilters();
});
'''


def build_html(results: list[dict], summary: dict, texts: dict[str, str], edh_texts: dict[str, dict]) -> str:
    total = len(results)
    n_err = sum(1 for r in results if result_has_error(r))

    cards_html = '\n'.join(render_result(r, texts, edh_texts) for r in results)

    f = summary.get('fields', {})

    def pct(num, den):
        return f'{num/den*100:.1f}%' if den else '—'

    summary_items = ''
    labels = [('praenomen','Praenomen'),('nomen','Nomen'),('cognomen','Cognomen'),('gender','Gender')]
    for fkey, flabel in labels:
        fd = f.get(fkey, {})
        match = fd.get('match', 0)
        mism  = fd.get('mismatch', 0)
        miss  = fd.get('missing', 0)
        total_pairs = fd.get('total', 0)
        acc = fd.get('accuracy', 0)
        cov = fd.get('coverage', 0)
        summary_items += f'''
      <div class="summary-item">
        <div class="summary-label">{flabel}</div>
        <div class="summary-value">{acc*100:.1f}%</div>
        <div class="summary-label">Acc | Cov {cov*100:.1f}%</div>
        <div class="summary-label">match={match} FP={mism} FN≈missing+edh_val</div>
      </div>'''

    return f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EDH vs CG Name Evaluation Viewer</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>EDH vs Career Graph — Name Component Evaluation</h1>
  <div class="subtitle">Africa Proconsularis + Numidia &nbsp;|&nbsp; {total} 碑文 &nbsp;|&nbsp; {summary.get('total_person_pairs', '?')} 人物ペア</div>
</header>

<div class="controls">
  <label><input type="checkbox" id="errOnly"> エラーのある碑文のみ表示</label>
  <label>HD番号検索: <input type="text" id="searchBox" placeholder="例: HD000379"></label>
  <label>絞り込み:
    <select id="errField">
      <option value="all">すべて</option>
      <option value="fp:">FP（誤り）あり</option>
      <option value="fn:">FN（欠落）あり</option>
    </select>
  </label>
  <button onclick="expandAll()">すべて展開</button>
  <button onclick="collapseAll()">すべて折りたたむ</button>
  <span class="count-info" id="visCount">{total} 件表示中</span>
</div>

<div class="legend">
  <div class="legend-item"><span class="legend-swatch" style="background:var(--match)"></span> 一致 (match)</div>
  <div class="legend-item"><span class="legend-swatch" style="background:var(--fp)"></span> 誤り FP (mismatch)</div>
  <div class="legend-item"><span class="legend-swatch" style="background:var(--fn)"></span> 欠落 FN (EDHあり / CGなし)</div>
  <div class="legend-item"><span class="legend-swatch" style="background:var(--miss)"></span> 両方なし (missing)</div>
</div>

<main>
  <div class="summary-box">
    <h2>評価サマリー</h2>
    <div class="summary-grid">
      <div class="summary-item">
        <div class="summary-label">対象碑文</div>
        <div class="summary-value">{total}</div>
        <div class="summary-label">うちエラーあり: {n_err}</div>
      </div>
      <div class="summary-item">
        <div class="summary-label">人物ペア数</div>
        <div class="summary-value">{summary.get('total_person_pairs', '?')}</div>
        <div class="summary-label">人数一致率: {summary.get('person_count_match_pct', '?')}%</div>
      </div>
      {summary_items}
    </div>
  </div>

{cards_html}
</main>

<script>{JS}</script>
</body>
</html>'''


def main():
    print('Loading EDCS inscription texts ...')
    texts = load_inscription_texts()
    print(f'  Loaded {len(texts):,} EDCS texts')

    print('Loading EDH inscription texts ...')
    edh_texts = load_edh_texts()
    print(f'  Loaded {len(edh_texts):,} EDH texts')

    print(f'Loading evaluation results from {JSON_IN} ...')
    data    = json.loads(JSON_IN.read_text(encoding='utf-8'))
    summary = data.get('summary', {})
    results = data.get('results', [])
    print(f'  {len(results)} inscriptions')

    print('Building HTML ...')
    html = build_html(results, summary, texts, edh_texts)
    HTML_OUT.write_text(html, encoding='utf-8')
    print(f'Saved → {HTML_OUT}')
    print(f'  File size: {HTML_OUT.stat().st_size / 1024:.0f} KB')


if __name__ == '__main__':
    main()
