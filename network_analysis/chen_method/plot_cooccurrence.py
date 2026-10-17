#!/usr/bin/env python3
"""
Figures for the within-inscription co-occurrence networks (README sections 1-2, 1-3).

  --source benefactions (default)      --source positions
  fig5_pair_deviation                  fig8_position_deviation
  fig6_cooc_network                    fig9_position_network
  fig7_remap_gain                      (not applicable)

Both sources are the same measurement — observed co-occurrence against a
permutation baseline — so they share the plotting code and differ only in the
WORDING table. The position variant counts pairs across different people only,
and says so in the figure, because reading those ties as cursus steps inverts
their meaning.

fig5 carries the argument. The finding here is the opposite shape from the deity
and nomen networks: Louvain fails again (Q = 0.156 against a null of 0.186), so
there is no partition to draw, but 32 of 56 pairs deviate from the permutation
baseline. That is a per-pair result, and a ranked dot plot shows it directly --
a force-directed picture of a density-0.32 graph would show a blob and hide the
very thing that is significant.

The negative deviations matter as much as the positive ones: if pairs only ever
exceeded expectation the result could be a frequency artefact, so the figure
keeps both tails visible rather than cropping to the top N.

Deliberately not a network diagram as the lead figure. plot_network.py draws one
for the deity projection because there the question is whether clusters separate;
here the question is which specific pairs beat chance, which a graph layout
answers badly.

Usage:
    venv/bin/python network_analysis/chen_method/plot_cooccurrence.py
    venv/bin/python network_analysis/chen_method/plot_cooccurrence.py --level category
    venv/bin/python network_analysis/chen_method/plot_cooccurrence.py --source positions
"""

import argparse
import json
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# Same validated categorical palette as plot_network.py / plot_concentration.py.
# Re-checked for this use with scripts/validate_palette.js (light, #fcfcfb):
# all checks PASS, worst adjacent CVD dE 9.1 protan, normal-vision floor 19.6.
# The contrast WARN on the lighter slots is answered by direct labels, which
# every figure here carries.
SERIES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4']
GREY = '#b8b7b2'
SURFACE = '#fcfcfb'
INK = '#0b0b0b'
INK_2 = '#52514e'
GRID = '#d8d7d2'

# Positive and negative deviation are a polarity, so the two-hue diverging rule
# applies: one warm, one cool, and grey (not a third hue) for the middle.
POS = SERIES[1]   # observed above expectation
NEG = SERIES[0]   # observed below expectation
NEUTRAL = GREY    # |z| < 1.96

plt.rcParams.update({
    'figure.facecolor': SURFACE,
    'axes.facecolor': SURFACE,
    'savefig.facecolor': SURFACE,
    'font.size': 9,
    'text.color': INK,
    'axes.labelcolor': INK,
    'axes.edgecolor': GRID,
    'xtick.color': INK_2,
    'ytick.color': INK_2,
})

SIG = 1.96

# Wording per source. The figures are the same measurement either way — observed
# against a permutation baseline — so only the nouns change.
WORDING = {
    'benefactions': {
        'unit': 'object types',
        'xlabel': 'inscriptions containing both object types',
        'title5': 'Which benefaction types share an inscription more often than chance',
        'title6': 'Benefaction types co-occurring within one inscription',
        'note6': None,
    },
    'nomina': {
        'unit': 'gentilicia',
        'xlabel': 'inscriptions naming both families (non-kin ties only)',
        'title5': 'Which families appear together more often than chance',
        'title6': 'Gentilicia named together in one inscription',
        'note6': 'declared family ties excluded; -ius/-ia merged',
    },
    'cursus': {
        'unit': 'career steps',
        'xlabel': 'careers where the two posts were consecutive',
        'title5': 'Which posts follow one another in a career',
        'title6': 'Career steps adjacent in one person\'s cursus',
        'note6': 'adjacent steps only, undirected — ascending and descending '
                 'cursus are not distinguished',
    },
    'positions': {
        'unit': 'offices',
        'xlabel': 'inscriptions naming both offices (on different people)',
        'title5': 'Which offices appear together more often than chance',
        'title6': 'Offices held by different people named in one inscription',
        # The cross-person rule is the whole basis of this variant; a reader
        # who takes these for cursus steps reads the figure backwards.
        'note6': 'pairs counted only across different people — a single cursus is excluded',
    },
}


def short(label: str) -> str:
    """`structure/structure.bath` -> `bath`; keep the category only if bare.

    Also tidies the canonical gentilicium marker: build_nomen_cooccurrence
    writes the merged -ius/-ia form as `rutili-`, which is right for a data
    key and wrong on an axis. Shown as `Rutili(us/a)` instead.
    """
    if label.endswith('i-'):
        return label[:-2].capitalize() + 'i(us/a)'
    tail = label.split('/')[-1]
    return tail.split('.', 1)[1] if '.' in tail else tail


def pair_label(p) -> str:
    return f'{short(p["a"])} — {short(p["b"])}'


def colour_of(z) -> str:
    if z >= SIG:
        return POS
    if z <= -SIG:
        return NEG
    return NEUTRAL


def fig_pair_deviation(data, out: Path, top: int = 22, w=WORDING['benefactions']):
    """Observed vs expected per pair, ranked by z. The lead figure.

    A dumbbell rather than bars: the quantity of interest is the *gap* between
    what chance predicts and what the corpus shows, and two bars per pair would
    make the reader compute that difference themselves.
    """
    pairs = sorted(data['pairs'], key=lambda p: p['z'])
    # Keep both tails. Cropping to the largest positive z would drop the
    # avoidances, which are what rule out a pure frequency effect.
    if len(pairs) > top:
        half = top // 2
        pairs = pairs[:half] + pairs[-(top - half):]

    # Height tracks the row count, plus a fixed band for the title and the
    # legend that now sits under the x-axis.
    fig, ax = plt.subplots(figsize=(9.5, 0.33 * len(pairs) + 2.9))
    y = np.arange(len(pairs))

    for i, p in enumerate(pairs):
        c = colour_of(p['z'])
        ax.plot([p['expected'], p['obs']], [i, i], color=c, lw=2, zorder=2,
                solid_capstyle='round', alpha=0.55)
        # Expected: hollow, so the filled marker always reads as the observation.
        ax.plot(p['expected'], i, 'o', ms=6, mfc=SURFACE, mec=GREY, mew=1.4,
                zorder=3)
        ax.plot(p['obs'], i, 'o', ms=8, mfc=c, mec=SURFACE, mew=1.4, zorder=4)

    # Direct-label z only where it is significant: a number on all 22 rows is
    # the "value on every point" anti-pattern, and the non-significant rows are
    # the ones whose exact z nobody needs.
    for i, p in enumerate(pairs):
        if abs(p['z']) >= SIG:
            ax.annotate(f'z {p["z"]:+.1f}',
                        (max(p['obs'], p['expected']), i),
                        xytext=(9, 0), textcoords='offset points',
                        va='center', fontsize=7.5, color=INK_2)

    ax.set_yticks(y)
    ax.set_yticklabels([pair_label(p) for p in pairs], fontsize=8)
    ax.set_xlabel(w['xlabel'])

    n_pos = sum(1 for p in data['pairs'] if p['z'] >= SIG)
    n_neg = sum(1 for p in data['pairs'] if p['z'] <= -SIG)
    ax.set_title(
        w['title5'] + '\n'
        f'{n_pos} pairs above and {n_neg} below the permutation baseline, '
        f'of {len(data["pairs"])} tested',
        fontsize=11, color=INK, pad=12, loc='left')

    handles = [
        plt.Line2D([], [], marker='o', ls='none', ms=7, mfc=POS, mec=SURFACE,
                   label=f'more often than expected (z ≥ {SIG})'),
        plt.Line2D([], [], marker='o', ls='none', ms=7, mfc=NEG, mec=SURFACE,
                   label=f'less often than expected (z ≤ -{SIG})'),
        plt.Line2D([], [], marker='o', ls='none', ms=7, mfc=NEUTRAL,
                   mec=SURFACE, label='not significant'),
        plt.Line2D([], [], marker='o', ls='none', ms=6, mfc=SURFACE, mec=GREY,
                   mew=1.4, label='expected (500 permutations)'),
    ]
    # Below the axes, not inside: at 22 rows the plot area is full top to
    # bottom, and an inset legend sits on the last rows' labels. The offset is
    # in axes fractions, so it has to scale with the row count or it lands on
    # the x-axis label in the shorter (category-level) figure.
    axes_h = 0.33 * len(pairs)
    ax.legend(handles=handles, frameon=False, fontsize=8.2, labelcolor=INK_2,
              loc='upper left', bbox_to_anchor=(0, -0.85 / axes_h), ncol=2,
              borderaxespad=0, columnspacing=1.6, handletextpad=0.5)

    for s in ('top', 'right', 'left'):
        ax.spines[s].set_visible(False)
    ax.grid(axis='x', color=GRID, lw=0.6, alpha=0.6)
    ax.set_axisbelow(True)
    ax.margins(x=0.13, y=0.02)
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)


def fig_network(data, out: Path, w=WORDING['benefactions'], max_nodes=None):
    """The graph itself, with edges carrying z rather than raw co-occurrence.

    Drawn as a secondary figure and read with care: Louvain does not beat the
    null here, so no community colouring is applied. Colouring nodes by a
    partition the statistics reject would assert exactly what the data denies.
    """
    g = nx.Graph()
    for p in data['pairs']:
        g.add_edge(short(p['a']), short(p['b']), z=p['z'], obs=p['obs'])
    if g.number_of_edges() == 0:
        return

    # Cap the node count before layout. At position level the graph has ~100
    # nodes and a force layout turns into an unreadable hairball; keeping the
    # best-connected ones answers "which posts sit next to which" without
    # pretending the long tail is legible. Strength is summed |z|, so a node
    # survives on how strongly it deviates, not on raw frequency.
    if max_nodes and g.number_of_nodes() > max_nodes:
        strength = {n: sum(abs(g[n][m].get('z', 0)) for m in g[n]) for n in g}
        keep = sorted(strength, key=lambda n: -strength[n])[:max_nodes]
        dropped_n = g.number_of_nodes() - len(keep)
        g = g.subgraph(keep).copy()
    else:
        dropped_n = 0

    # Giant component only, as plot_network.py does: isolated pairs push the
    # part worth reading into a corner under a force layout. Noted in the
    # subtitle instead.
    comp = max(nx.connected_components(g), key=len)
    outside = sorted(set(g.nodes()) - comp)
    sub_g = g.subgraph(comp)

    fig, ax = plt.subplots(figsize=(9.6, 8.2))
    pos = nx.spring_layout(sub_g, weight=None, seed=7, k=1.6, iterations=500)
    g = sub_g

    sig_edges = [(u, v) for u, v, d in g.edges(data=True) if abs(d['z']) >= SIG]
    dim_edges = [(u, v) for u, v, d in g.edges(data=True) if abs(d['z']) < SIG]

    # Non-significant ties stay visible but recede: dropping them would imply
    # the graph is sparser than it is (density 0.32 is the point of comparison
    # with the 0.945 that sank the object x place attempt).
    nx.draw_networkx_edges(g, pos, edgelist=dim_edges, ax=ax, width=0.5,
                           edge_color=GRID, alpha=0.7)
    for u, v in sig_edges:
        z = g[u][v]['z']
        nx.draw_networkx_edges(
            g, pos, edgelist=[(u, v)], ax=ax,
            width=min(0.8 + abs(z) * 0.28, 5.0),
            edge_color=POS if z > 0 else NEG,
            alpha=0.75 if z > 0 else 0.85)

    deg = dict(g.degree())
    nx.draw_networkx_nodes(
        g, pos, ax=ax,
        node_size=[70 + 26 * deg[n] for n in g.nodes()],
        node_color=SURFACE, edgecolors=INK_2, linewidths=0.9)
    # Offset labels with a surface-coloured backing box. Centred labels collide
    # badly once the core nodes sit close together.
    for n, (x, y) in pos.items():
        ax.annotate(n, (x, y), xytext=(0, 9), textcoords='offset points',
                    ha='center', va='bottom', fontsize=7.8, color=INK,
                    bbox=dict(boxstyle='round,pad=0.14', fc=SURFACE,
                              ec='none', alpha=0.82), zorder=5)

    # null_mean is absent when the build ran with --null-trials 0.
    q, null = data.get('modularity'), data.get('null_mean')
    if q is None:
        sub = 'edge colour and width = permutation z, not raw count'
    elif null is None:
        sub = (f'Louvain Q = {q:.3f}; no partition is drawn\n'
               'edge colour and width = permutation z, not raw count')
    else:
        sub = (f'Louvain Q = {q:.3f} against a null of {null:.3f} — no partition '
               'is drawn\nedge colour and width = permutation z, not raw count')
    if dropped_n:
        sub += (f'\nshowing the {g.number_of_nodes()} most strongly tied of '
                f'{g.number_of_nodes() + dropped_n} nodes')
    if outside:
        # `outside` already holds display labels: fig_network builds g from
        # short(p['a']) / short(p['b']). Re-shortening would mangle them.
        names = list(outside)
        # Wrapped and capped: with merged gentilicia the names are long and an
        # unwrapped list runs off the right edge of the figure.
        shown = names[:4]
        more = f' +{len(names) - 4} more' if len(names) > 4 else ''
        sub += ('\nnot shown (isolated from the main component): '
                + ', '.join(shown) + more)
    if w['note6']:
        sub += '\n' + w['note6']
    ax.set_title(w['title6'] + '\n' + sub,
                 fontsize=11, color=INK, pad=14, loc='left')

    handles = [
        plt.Line2D([], [], color=POS, lw=3, label=f'z ≥ {SIG}'),
        plt.Line2D([], [], color=NEG, lw=3, label=f'z ≤ -{SIG}'),
        plt.Line2D([], [], color=GRID, lw=1.2, label='not significant'),
    ]
    # Below the axes: with few nodes the spring layout spreads them to the
    # corners and an inset legend lands on a node label.
    ax.legend(handles=handles, frameon=False, fontsize=8.5, labelcolor=INK_2,
              loc='upper left', bbox_to_anchor=(0, -0.01), ncol=3,
              borderaxespad=0, columnspacing=2.0, handletextpad=0.6)
    ax.axis('off')
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)


def fig_remap_gain(raw, remapped, out: Path):
    """What routing `other` through the category map recovers.

    Two measures on different scales would be a dual axis, so this is a grouped
    bar on one count axis instead.
    """
    if raw is None:
        return
    labels = ['inscriptions with\na usable label', 'inscriptions with\n2+ distinct types']
    before = [raw['inscriptions_labelled'], raw['inscriptions_multi']]
    after = [remapped['inscriptions_labelled'], remapped['inscriptions_multi']]

    fig, ax = plt.subplots(figsize=(7.8, 3.6))
    y = np.arange(len(labels))
    h = 0.22   # thin marks; full-height blocks read loud at this few bars
    # 2px-equivalent surface gap between the paired bars, not a border.
    ax.barh(y + h / 2 + 0.012, before, height=h, color=GREY,
            label='raw object_type', zorder=2)
    ax.barh(y - h / 2 - 0.012, after, height=h, color=SERIES[0],
            label='after remap (subtype)', zorder=2)

    for yy, v in zip(y + h / 2 + 0.012, before):
        ax.annotate(f'{v:,}', (v, yy), xytext=(6, 0),
                    textcoords='offset points', va='center',
                    fontsize=8.5, color=INK_2)
    for yy, v in zip(y - h / 2 - 0.012, after):
        ax.annotate(f'{v:,}', (v, yy), xytext=(6, 0),
                    textcoords='offset points', va='center',
                    fontsize=8.5, color=INK)

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel('inscriptions')
    total = remapped.get('objects_total')
    sub = (f'from {total:,} benefaction objects across the corpus'
           if total else 'object_type `other` resolved by surface form')
    ax.set_title('What the object_category_map remap recovers\n' + sub,
                 fontsize=11, color=INK, pad=12, loc='left')
    # Under the axis: an inset legend lands on the longest bar and its value.
    ax.legend(frameon=False, fontsize=8.5, labelcolor=INK_2,
              loc='upper left', bbox_to_anchor=(0, -0.16), ncol=2,
              borderaxespad=0, columnspacing=1.6, handletextpad=0.5)
    for s in ('top', 'right', 'left'):
        ax.spines[s].set_visible(False)
    ax.grid(axis='x', color=GRID, lw=0.6, alpha=0.6)
    ax.set_axisbelow(True)
    ax.margins(x=0.16, y=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)


def load(outdir: Path, tag: str):
    path = outdir / f'{tag}.json'
    if not path.exists():
        return None
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--source',
                    choices=('benefactions', 'positions', 'nomina', 'cursus'),
                    default='benefactions',
                    help='which build script\'s output to plot')
    ap.add_argument('--level',
                    choices=('category', 'subtype', 'abstract', 'type'),
                    default='subtype',
                    help='benefactions: category/subtype; '
                         'cursus: position (default) / abstract / type')
    ap.add_argument('--max-nodes', type=int, default=None,
                    help='cap nodes in the network figure (default: all; '
                         'useful at position level, where there are ~100)')
    ap.add_argument('--top', type=int, default=22,
                    help='pairs to show in fig5 (both tails kept)')
    ap.add_argument('--province', default=None,
                    help='plot a province-restricted run, e.g. "Numidia"')
    ap.add_argument('--out', default=str(HERE / 'output'))
    args = ap.parse_args()

    outdir = Path(args.out)
    w = dict(WORDING[args.source])
    # Province goes in the title, not just the filename: the two provinces give
    # visibly different networks and an unlabelled figure invites mixing them up.
    prov_tag = ('_' + re.sub(r'\W+', '_', args.province.lower())
                if args.province else '')
    if args.province:
        w['title5'] = f'{w["title5"]} — {args.province}'
        w['title6'] = f'{w["title6"]} — {args.province}'

    if args.source == 'cursus':
        base = {'type': 'cursus_type', 'abstract': 'cursus_abstract'}.get(
            args.level, 'cursus')
        tag, suffix, prefix = base + prov_tag, '', 'fig12'
        hint = ('build_cursus_network.py'
                + (f' --province "{args.province}"' if args.province else ''))
    elif args.source == 'nomina':
        tag, suffix, prefix = 'nomen_cooc' + prov_tag, '', 'fig10'
        hint = ('build_nomen_cooccurrence.py'
                + (f' --province "{args.province}"' if args.province else ''))
    elif args.source == 'positions':
        tag, suffix, prefix = 'pos' + prov_tag, '', 'fig8'
        hint = ('build_position_cooccurrence.py'
                + (f' --province "{args.province}"' if args.province else ''))
    else:
        tag = 'cooc_subtype' if args.level == 'subtype' else 'cooc'
        suffix = '' if args.level == 'subtype' else '_category'
        prefix = 'fig5'
        hint = f'build_cooccurrence_network.py --level {args.level}'

    data = load(outdir, tag)
    if data is None:
        print(f'missing {outdir}/{tag}.json — run {hint} first', file=sys.stderr)
        return 1

    written = []
    if args.source == 'cursus':
        sec = {'type': '_type', 'abstract': '_abstract'}.get(args.level, '')
        dev = outdir / f'fig12_cursus_deviation{sec}{prov_tag}.png'
        net = outdir / f'fig13_cursus_network{sec}{prov_tag}.png'
    elif args.source == 'nomina':
        dev = outdir / f'fig10_nomen_deviation{prov_tag}.png'
        net = outdir / f'fig11_nomen_network{prov_tag}.png'
    elif args.source == 'positions':
        # fig8/fig9 rather than reusing fig5/fig6: both sets live in one output
        # directory and the benefaction figures are referenced by number in the
        # README.
        dev = outdir / f'fig8_position_deviation{prov_tag}.png'
        net = outdir / f'fig9_position_network{prov_tag}.png'
    else:
        dev = outdir / f'fig5_pair_deviation{suffix}.png'
        net = outdir / f'fig6_cooc_network{suffix}.png'

    fig_pair_deviation(data, dev, args.top, w)
    written.append(dev.name)
    fig_network(data, net, w, args.max_nodes)
    written.append(net.name)

    if args.source == 'benefactions':
        raw = load(outdir, 'cooc_raw')
        if raw is not None and 'inscriptions_labelled' in raw:
            gain = outdir / f'fig7_remap_gain{suffix}.png'
            fig_remap_gain(raw, data, gain)
            written.append(gain.name)
        elif raw is not None:
            print('cooc_raw.json predates inscriptions_labelled — rerun '
                  'build_cooccurrence_network.py --no-remap to get fig7',
                  file=sys.stderr)

    print(f'written: {outdir}/' + ', '.join(written))
    return 0


if __name__ == '__main__':
    sys.exit(main())
