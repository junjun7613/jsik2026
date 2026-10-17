#!/usr/bin/env python3
"""
Figures for the deity x place network (Chen 2023 method).

Three figures, each answering a question the README states in numbers:

  fig1_two_mode     what the bipartite network looks like (Chen's Figure 1)
  fig2_deity        the deity-deity projection, coloured by Louvain cluster
  fig3_null         observed modularity against the degree-preserving null

Figure 3 carries the argument. The finding is negative — no sub-regional
clusters — and a reader has to see that the observed Q sits inside, or below,
the distribution produced by chance before that claim is credible.

Layout follows Chen: force-directed, which for a projection this dense says
more about what fails to separate than about fine structure. Spring layout
stands in for Gephi's Force Atlas 2 Lin-Log.

Usage:
    venv/bin/python network_analysis/chen_method/plot_network.py
    venv/bin/python network_analysis/chen_method/plot_network.py --province Numidia
"""

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from build_deity_network import (  # noqa: E402
    CORPUS, build_two_mode, is_imperial, iter_deities, louvain,
    null_modularity, project,
)

# Categorical slots 1-5 from the reference palette, validated for this use:
# node colour carries cluster identity. Validator (light, #fcfcfb surface)
# reports all checks PASS; worst adjacent CVD dE 9.1 (protan), normal-vision
# floor 19.6. The contrast WARN on slots 3-5 is answered by direct labels,
# which the figures carry anyway.
SERIES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4']
GREY = '#8a8a85'         # nodes outside the labelled clusters
SURFACE = '#fcfcfb'
INK = '#0b0b0b'
INK_2 = '#52514e'
GRID = '#d8d7d2'

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


def cluster_colours(comms, min_size=3):
    """
    Map node -> colour. Only clusters big enough to read get a hue.

    Chen's clusters are substantive groupings; here most nodes fall into two
    or three large components and the rest are pairs. Giving every pair its own
    hue would imply a structure the modularity score says is not there, so
    small clusters are greyed and the legend reports how many were folded.
    """
    colours, named, folded = {}, 0, 0
    for comm in comms:
        if len(comm) >= min_size and named < len(SERIES):
            for n in comm:
                colours[n] = SERIES[named]
            named += 1
        else:
            for n in comm:
                colours[n] = GREY
            folded += 1
    return colours, named, folded


def fig_two_mode(two, out: Path, scope: str):
    """Chen's Figure 1: the bipartite network, places vs deities."""
    fig, ax = plt.subplots(figsize=(9, 7.5))
    pos = nx.spring_layout(two, seed=42, k=0.42, iterations=220)

    places = [n for n, d in two.nodes(data=True) if d['kind'] == 'place']
    deities = [n for n, d in two.nodes(data=True) if d['kind'] == 'deity']

    nx.draw_networkx_edges(two, pos, ax=ax, edge_color=GRID, width=0.5, alpha=0.7)
    nx.draw_networkx_nodes(two, pos, nodelist=places, ax=ax, node_shape='s',
                           node_size=22, node_color=SERIES[0],
                           edgecolors=SURFACE, linewidths=0.5, label='place')
    nx.draw_networkx_nodes(two, pos, nodelist=deities, ax=ax, node_shape='o',
                           node_size=[18 + 7 * two.degree(n) for n in deities],
                           node_color=SERIES[1], edgecolors=SURFACE,
                           linewidths=0.5, label='deity')

    # Label only the hubs, fanned radially: they cluster in the core, so
    # labels placed at the node overprint each other.
    top = sorted(deities, key=lambda n: -two.degree(n))[:10]
    for i, n in enumerate(top):
        x, y = pos[n]
        ang = 2 * np.pi * i / len(top)
        dx, dy = 62 * np.cos(ang), 62 * np.sin(ang)
        ax.annotate(n[1], (x, y), fontsize=7.5, color=INK,
                    ha='left' if dx > 0 else 'right', va='center',
                    xytext=(dx, dy), textcoords='offset points',
                    arrowprops=dict(arrowstyle='-', color=INK_2,
                                    lw=0.5, alpha=0.8, shrinkA=0, shrinkB=3),
                    bbox=dict(boxstyle='round,pad=0.2', fc=SURFACE,
                              ec='none', alpha=0.9))

    dens = two.number_of_edges() / max(len(places) * len(deities), 1)
    ax.set_title(f'Deity × place network — {scope}\n'
                 f'{len(places)} places × {len(deities)} deities, '
                 f'{two.number_of_edges()} ties, density {dens:.3f}\n'
                 f'Chen 2023: 56 × 83, density 0.081',
                 fontsize=10.5, color=INK, pad=12)
    ax.legend(loc='upper left', frameon=False, fontsize=8.5, labelcolor=INK_2)
    ax.axis('off')
    ax.margins(0.1)
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)


def fig_projection(proj, comms, q, out: Path, scope: str):
    """The deity-deity projection, coloured by Louvain cluster."""
    fig, ax = plt.subplots(figsize=(9, 8))

    # Draw the giant component only. A handful of isolated pairs sit far from
    # everything else and, in a force layout, push the part worth reading into
    # a corner. They are reported in the caption instead.
    comp = max(nx.connected_components(proj), key=len)
    outside = proj.number_of_nodes() - len(comp)
    sub = proj.subgraph(comp)
    comms_sub = [c & comp for c in comms if c & comp]
    comms_sub.sort(key=len, reverse=True)

    pos = nx.spring_layout(sub, seed=42, k=1.5, iterations=400, weight='weight')
    colours, named, folded = cluster_colours(comms_sub)

    weights = np.array([d['weight'] for _, _, d in sub.edges(data=True)])
    widths = 0.15 + 1.1 * (weights / weights.max()) if len(weights) else []
    nx.draw_networkx_edges(sub, pos, ax=ax, edge_color=GRID,
                           width=widths, alpha=0.32)
    nx.draw_networkx_nodes(
        sub, pos, ax=ax,
        node_size=[14 + 2.2 * sub.degree(n, weight='weight') ** 0.6
                   for n in sub.nodes()],
        node_color=[colours.get(n, GREY) for n in sub.nodes()],
        edgecolors=SURFACE, linewidths=0.6)

    # Label the hubs, nudged apart: at this density the top nodes sit almost
    # on top of one another and unnudged labels overprint into a blur.
    # The hubs sit almost on top of one another in the core, so labels are
    # fanned radially outward from the centroid rather than stacked upward:
    # a vertical ladder of leader lines is as unreadable as overprinting.
    top = sorted(sub.nodes(), key=lambda n: -sub.degree(n, weight='weight'))[:12]
    cx = float(np.mean([p[0] for p in pos.values()]))
    cy = float(np.mean([p[1] for p in pos.values()]))
    for i, n in enumerate(top):
        x, y = pos[n]
        ang = 2 * np.pi * i / len(top)
        r = 58
        dx, dy = r * np.cos(ang), r * np.sin(ang)
        ax.annotate(str(n), (x, y), fontsize=7.5, color=INK,
                    ha='left' if dx > 0 else 'right', va='center',
                    xytext=(dx, dy), textcoords='offset points',
                    arrowprops=dict(arrowstyle='-', color=INK_2,
                                    lw=0.5, alpha=0.8, shrinkA=0, shrinkB=3),
                    bbox=dict(boxstyle='round,pad=0.2', fc=SURFACE,
                              ec='none', alpha=0.9))

    handles = [plt.Line2D([], [], marker='o', ls='', markersize=7,
                          markerfacecolor=SERIES[i], markeredgecolor=SURFACE,
                          label=f'cluster {i+1} (n={len(comms_sub[i])})')
               for i in range(named)]
    if folded:
        handles.append(plt.Line2D([], [], marker='o', ls='', markersize=7,
                                  markerfacecolor=GREY, markeredgecolor=SURFACE,
                                  label=f'{folded} clusters of < 3'))
    ax.legend(handles=handles, loc='upper left', frameon=False,
              fontsize=8.5, labelcolor=INK_2)

    note = (f'\n{outside} further deities in detached pairs, not drawn'
            if outside else '')
    ax.set_title(f'Deity–deity projection — {scope}\n'
                 f'{proj.number_of_nodes()} deities, density '
                 f'{nx.density(proj):.3f}, Louvain Q = {q:.3f}\n'
                 f'Q < 0.20 → no community structure{note}',
                 fontsize=10.5, color=INK, pad=12)
    ax.axis('off')
    ax.margins(0.12)
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)


def fig_null(q, nulls, out: Path, scope: str):
    """
    Observed modularity against the degree-preserving null.

    This is the figure the negative finding rests on: the reader needs to see
    that the observed Q is not merely low but lower than chance produces.
    """
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    mean, sd = float(np.mean(nulls)), float(np.std(nulls))
    z = (q - mean) / sd if sd else float('nan')

    ax.hist(nulls, bins=14, color=GRID, edgecolor=SURFACE, linewidth=1.2,
            label=f'rewired networks (n={len(nulls)})')

    # Pad the x-range so the observed marker and its label sit inside the axes
    # even when Q falls well outside the null distribution, as it does here.
    lo, hi = min(min(nulls), q), max(max(nulls), q)
    pad = (hi - lo) * 0.18 or 0.01
    ax.set_xlim(lo - pad, hi + pad)
    top = ax.get_ylim()[1]
    ax.set_ylim(0, top * 1.18)

    ax.axvline(mean, color=INK_2, lw=1.4, ls='--')
    ax.annotate(f'null mean {mean:.3f}', (mean, top * 1.1),
                fontsize=8.5, color=INK_2, ha='center',
                bbox=dict(boxstyle='round,pad=0.2', fc=SURFACE, ec='none'))
    ax.axvline(q, color=SERIES[1], lw=2.4)
    # Label sits on the side with empty space: away from the null distribution.
    ax.annotate(f'observed Q = {q:.3f}\nz = {z:+.2f}',
                (q, top * 0.62), fontsize=9, color=INK,
                ha='left' if q < mean else 'right',
                xytext=(9 if q < mean else -9, 0), textcoords='offset points',
                bbox=dict(boxstyle='round,pad=0.3', fc=SURFACE,
                          ec=SERIES[1], lw=1.1))

    verdict = ('below chance — the network is more homogeneous than '
               'degree alone predicts' if z < 0 else
               'above chance')
    ax.set_title(f'Modularity against a degree-preserving null — {scope}\n'
                 f'{verdict}', fontsize=11, color=INK, pad=12)
    ax.set_xlabel('Louvain modularity Q')
    ax.set_ylabel('rewirings')
    ax.legend(frameon=False, fontsize=8.5, labelcolor=INK_2, loc='upper left')
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    ax.grid(axis='y', color=GRID, lw=0.6, alpha=0.6)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--province', default=None)
    ap.add_argument('--include-imperial', action='store_true')
    ap.add_argument('--null-trials', type=int, default=60)
    ap.add_argument('--out', default=str(HERE / 'output'))
    args = ap.parse_args()

    raw = list(iter_deities(CORPUS, args.province))
    imperial = {d for _, d in raw if is_imperial(d)}
    pairs = raw if args.include_imperial else [(p, d) for p, d in raw
                                               if d not in imperial]
    two = build_two_mode(pairs, 2, 2)
    if two.number_of_edges() == 0:
        print('empty network')
        return 1

    proj = project(two, 'deity')
    comms, q = louvain(proj)
    nulls = null_modularity(two, 'deity', args.null_trials)

    scope = args.province or 'North Africa'
    if args.include_imperial:
        scope += ' (incl. imperial)'
    slug = (args.province or 'all').lower().replace(' ', '_')
    if args.include_imperial:
        slug += '_imperial'

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    fig_two_mode(two, outdir / f'fig1_two_mode_{slug}.png', scope)
    fig_projection(proj, comms, q, outdir / f'fig2_deity_{slug}.png', scope)
    if nulls:
        fig_null(q, nulls, outdir / f'fig3_null_{slug}.png', scope)

    print(f'{scope}: Q={q:.3f}, {len(comms)} clusters, '
          f'null mean={np.mean(nulls):.3f} (n={len(nulls)})')
    print(f'written: {outdir}/fig[123]_*_{slug}.png')
    return 0


if __name__ == '__main__':
    sys.exit(main())
