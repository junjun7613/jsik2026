#!/usr/bin/env python3
"""
Maps of gentilicium concentration.

Companion to concentration.py. Three figures:

  map1_overview   every attestation place, with the spatially clustered names'
                  centroids over it — where the concentrated families sit
  map2_examples   small multiples: one panel per name, the actual attestation
                  points, sized by count
  fig4_scatter    dispersion against entropy, which separates the two regimes
                  numerically rather than geographically

The scatter is the one that carries the argument. A map shows that Sittius is
around Cirta, which an epigrapher already knows; the scatter shows that the
corpus splits into a concentrated and a dispersed population at all, and that
the split is not an artefact of how many places a name reaches.

Provincial boundaries come from the Pleiades/Pelagios region polygons already
in the repository (pipeline/case_study/), drawn directly from GeoJSON — cartopy
and geopandas are absent, and a province outline orients a reader far better
than a coastline would here, since the question is regional.

Usage:
    venv/bin/python network_analysis/chen_method/plot_concentration.py
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from build_nomen_network import CORPUS, is_imperial_nomen, iter_nomina  # noqa: E402
from concentration import load_coords  # noqa: E402

# Categorical slots 1-5, validated (see plot_network.py).
SERIES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4']
GREY = '#b8b7b2'
SURFACE = '#ffffff'
INK = '#0b0b0b'
INK_2 = '#52514e'
GRID = '#d8d7d2'

# Anchors so a reader can place the region without a coastline.
ANCHORS = {
    'Carthago': (36.85, 10.32),
    'Cirta': (36.36, 6.61),
    'Thibilis': (36.39, 7.25),
    'Lambaesis': (35.49, 6.25),
    'Thugga': (35.83, 9.01),
    'Thamugadi': (35.49, 6.47),
}

plt.rcParams.update({
    'figure.facecolor': SURFACE, 'axes.facecolor': SURFACE,
    'savefig.facecolor': SURFACE, 'font.size': 9, 'text.color': INK,
    'axes.labelcolor': INK, 'axes.edgecolor': GRID,
    'xtick.color': INK_2, 'ytick.color': INK_2,
})


REGIONS_GEOJSON = (HERE.parent.parent / 'pipeline' / 'case_study'
                   / 'pleiades-regions-magis-pelagios.geojson')

# Provinces relevant to this corpus. Pleiades carries several overlapping
# polygons per province (different periods and sources); all are drawn, which
# is why the outlines are sketched rather than authoritative.
AFRICAN_REGIONS = ('Africa', 'Numidia', 'Mauretania', 'Byzacena', 'Tripolitana')


def load_regions(path=REGIONS_GEOJSON):
    """Yield (name, [ring, ...]) for the North African provinces."""
    if not path.exists():
        return []
    try:
        data = json.load(open(path, encoding='utf-8'))
    except Exception:
        return []
    out = []
    for feat in data.get('features', []):
        name = (feat.get('properties') or {}).get('name', '')
        if not any(k in name for k in AFRICAN_REGIONS):
            continue
        geom = feat.get('geometry') or {}
        # Polygon coordinates nest one level, MultiPolygon two; taking only
        # the first ring would silently drop most of a MultiPolygon.
        if geom.get('type') == 'Polygon':
            rings = geom['coordinates']
        elif geom.get('type') == 'MultiPolygon':
            rings = [r for part in geom['coordinates'] for r in part]
        else:
            continue
        out.append((name, [r for r in rings if len(r) >= 3]))
    return out


def draw_regions(ax, regions, lw=0.8, label=False):
    """
    Province outlines as a recessive basemap.

    Outline only, on a white surface. A land fill competes with the grey
    attestation points for the same visual channel — the points are the data,
    the provinces only orient the reader.
    """
    for name, rings in regions:
        for ring in rings:
            xs = [p[0] for p in ring]
            ys = [p[1] for p in ring]
            ax.plot(xs + xs[:1], ys + ys[:1], color=INK_2, lw=lw,
                    alpha=0.45, zorder=1)
    if label:
        seen = set()
        for name, rings in regions:
            short = name.split('(')[0].strip()
            if short in seen:
                continue
            seen.add(short)
            biggest = max(rings, key=len)
            cx = float(np.mean([p[0] for p in biggest]))
            cy = float(np.mean([p[1] for p in biggest]))
            ax.annotate(short, (cx, cy), fontsize=7, color=INK_2,
                        style='italic', ha='center', zorder=2, alpha=0.9)


def aspect(ax, lat):
    """Equal-area-ish aspect for a lat/lon plot at this latitude."""
    ax.set_aspect(1 / np.cos(np.radians(lat)))


def draw_anchors(ax, fontsize=7):
    for name, (la, lo) in ANCHORS.items():
        ax.plot(lo, la, marker='*', ms=9, color=INK_2,
                markeredgecolor=SURFACE, markeredgewidth=0.6, zorder=5)
        ax.annotate(name, (lo, la), fontsize=fontsize, color=INK_2,
                    xytext=(4, 4), textcoords='offset points', zorder=6)


def core_extent(coords, place_counts, q=0.01):
    """
    Bounds covering the bulk of attestations, ignoring the long tail.

    A handful of places sit in Mauretania Tingitana and Tripolitania, 2000 km
    from the rest. Fitting the axes to them shrinks the region where almost
    every inscription was found to an illegible smudge, so the extent is taken
    from percentiles and the outliers are reported in the caption instead.
    """
    lons = np.array([coords[p][1] for p in place_counts])
    lats = np.array([coords[p][0] for p in place_counts])
    x0, x1 = np.quantile(lons, [q, 1 - q])
    y0, y1 = np.quantile(lats, [q, 1 - q])
    mx, my = (x1 - x0) * 0.06, (y1 - y0) * 0.10
    outside = int(((lons < x0) | (lons > x1) | (lats < y0) | (lats > y1)).sum())
    return (x0 - mx, x1 + mx), (y0 - my, y1 + my), outside


def map_overview(rows, coords, place_counts, regions, out: Path):
    """All attestation places, with clustered names' centroids on top."""
    fig, ax = plt.subplots(figsize=(11, 6))
    xlim, ylim, outside = core_extent(coords, place_counts)
    draw_regions(ax, regions, label=True)

    lons = [coords[p][1] for p in place_counts]
    lats = [coords[p][0] for p in place_counts]
    sizes = [3 + 1.9 * np.sqrt(place_counts[p]) for p in place_counts]
    ax.scatter(lons, lats, s=sizes, c=GREY, linewidths=0, alpha=0.7,
               label=f'attestation place (n={len(place_counts)})', zorder=2)

    sig = [r for r in rows
           if r.get('morans_z') is not None and r['morans_z'] > 1.96
           and r.get('centroid')]
    sig.sort(key=lambda r: -r['morans_z'])

    # Dispersion is shown by marker size, not by drawn circles: 44 overlapping
    # circles read as a scribble and hide the points underneath.
    ax.scatter([r['centroid'][1] for r in sig], [r['centroid'][0] for r in sig],
               s=[320 / max(r['dispersion_km'], 30) * 6 for r in sig],
               c=SERIES[1], edgecolors=SURFACE, linewidths=0.8, alpha=0.85,
               label=f'centroid of a spatially clustered name (n={len(sig)});'
                     f' larger = tighter', zorder=4)

    # Label the tightest, spread around the point to avoid overprinting.
    for i, r in enumerate(sorted(sig, key=lambda r: r['dispersion_km'])[:7]):
        la, lo = r['centroid']
        ang = 2 * np.pi * i / 7
        ax.annotate(f"{r['nomen']} · {r['dispersion_km']:.0f} km",
                    (lo, la), fontsize=7.5, color=INK,
                    ha='left' if np.cos(ang) > 0 else 'right', va='center',
                    xytext=(46 * np.cos(ang), 46 * np.sin(ang)),
                    textcoords='offset points', zorder=7,
                    arrowprops=dict(arrowstyle='-', color=INK_2, lw=0.5,
                                    alpha=0.8, shrinkA=0, shrinkB=3),
                    bbox=dict(boxstyle='round,pad=0.2', fc=SURFACE,
                              ec='none', alpha=0.9))

    draw_anchors(ax)
    ax.set_xlim(*xlim); ax.set_ylim(*ylim)
    aspect(ax, 35)
    ax.set_xlabel('longitude'); ax.set_ylabel('latitude')
    note = f'  ·  {outside} outlying places beyond this extent' if outside else ''
    ax.set_title('Where the spatially clustered gentilicia sit\n'
                 f"centroids of the {len(sig)} names with Moran's z > 1.96{note}",
                 fontsize=11, color=INK, pad=12)
    ax.legend(loc='lower left', frameon=False, fontsize=8, labelcolor=INK_2)
    ax.grid(color=GRID, lw=0.5, alpha=0.5)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)


def map_examples(rows, coords, by_name, regions, out: Path, n_panels=6):
    """One panel per name: the attestations themselves, not a summary."""
    sig = sorted((r for r in rows
                  if r.get('morans_z') is not None and r['morans_z'] > 1.96),
                 key=lambda r: -r['morans_z'])[:n_panels // 2]
    disp = sorted((r for r in rows if r.get('dispersion_km')),
                  key=lambda r: -r['dispersion_km'])[:n_panels - len(sig)]
    picks = [(r, True) for r in sig] + [(r, False) for r in disp]

    place_counts = Counter()
    for nm, pc in by_name.items():
        for p in pc:
            if p in coords:
                place_counts[p] += 1
    xlim, ylim, _ = core_extent(coords, place_counts)
    all_lon = [coords[p][1] for p in place_counts]
    all_lat = [coords[p][0] for p in place_counts]

    ncol = 3
    nrow = int(np.ceil(len(picks) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(13, 3.3 * nrow))
    axes = np.atleast_1d(axes).ravel()

    for ax, (r, clustered) in zip(axes, picks):
        draw_regions(ax, regions, lw=0.5)
        ax.scatter(all_lon, all_lat, s=1.2, c=GRID, linewidths=0, zorder=2)
        pc = by_name[r['nomen']]
        pts = [(coords[p][1], coords[p][0], c) for p, c in pc.items() if p in coords]
        if pts:
            ax.scatter([p[0] for p in pts], [p[1] for p in pts],
                       s=[6 + 5 * np.sqrt(p[2]) for p in pts],
                       c=SERIES[1] if clustered else SERIES[0],
                       edgecolors=SURFACE, linewidths=0.4, alpha=0.9, zorder=3)
        for (la, lo) in ANCHORS.values():
            ax.plot(lo, la, marker='*', ms=5, color=INK_2, zorder=4)
        ax.set_xlim(*xlim); ax.set_ylim(*ylim)
        aspect(ax, 35)
        tag = 'clustered' if clustered else 'dispersed'
        z = f"z={r['morans_z']:.1f}" if r.get('morans_z') is not None else 'z=—'
        ax.set_title(f"{r['nomen']}  ({tag})\n"
                     f"n={r['total']}, {r['places']} places, "
                     f"{r['dispersion_km']:.0f} km, {z}",
                     fontsize=9, color=INK, pad=6)
        ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values():
            s.set_color(GRID)
    for ax in axes[len(picks):]:
        ax.axis('off')

    fig.suptitle('Concentrated and dispersed gentilicia, same map extent  '
                 '(grey = all attestation places, ★ = reference cities)',
                 fontsize=11, color=INK, y=0.99)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out, dpi=200)
    plt.close(fig)


def fig_scatter(rows, out: Path):
    """Dispersion against entropy — the two regimes, measured not mapped."""
    pts = [r for r in rows if r.get('dispersion_km')]
    fig, ax = plt.subplots(figsize=(8.5, 5.6))

    sig = [r for r in pts if r.get('morans_z') is not None and r['morans_z'] > 1.96]
    ns = [r for r in pts if r not in sig]
    ax.scatter([r['entropy'] for r in ns], [r['dispersion_km'] for r in ns],
               s=[8 + 1.6 * np.sqrt(r['total']) for r in ns],
               c=GREY, edgecolors=SURFACE, linewidths=0.5,
               label=f'not spatially clustered (n={len(ns)})', zorder=2)
    ax.scatter([r['entropy'] for r in sig], [r['dispersion_km'] for r in sig],
               s=[8 + 1.6 * np.sqrt(r['total']) for r in sig],
               c=SERIES[1], edgecolors=SURFACE, linewidths=0.5,
               label=f"Moran's z > 1.96 (n={len(sig)})", zorder=3)

    for r in sorted(sig, key=lambda r: -r['morans_z'])[:5] + \
             sorted(pts, key=lambda r: -r['dispersion_km'])[:3]:
        ax.annotate(r['nomen'], (r['entropy'], r['dispersion_km']),
                    fontsize=7.5, color=INK, xytext=(5, 4),
                    textcoords='offset points',
                    bbox=dict(boxstyle='round,pad=0.18', fc=SURFACE,
                              ec='none', alpha=0.85))

    ax.set_xlabel('normalised entropy  (0 = one place, 1 = even spread)')
    ax.set_ylabel('mean distance from centroid (km)')
    # Not two discrete groups: the corpus forms a continuum from tight local
    # families to names spread over the whole province. Calling it "two
    # regimes", as an earlier draft did, overstates what the plot shows.
    ax.set_title('Gentilicium distribution: a continuum, not two groups\n'
                 'marker size = number of attestations',
                 fontsize=11, color=INK, pad=12)
    ax.legend(frameon=False, fontsize=8.5, labelcolor=INK_2, loc='upper left')
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    ax.grid(color=GRID, lw=0.6, alpha=0.6)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--results', default=str(HERE / 'output' / 'concentration.json'))
    ap.add_argument('--out', default=str(HERE / 'output'))
    args = ap.parse_args()

    rows = json.load(open(args.results, encoding='utf-8'))
    coords = load_coords(CORPUS)

    by_name = defaultdict(Counter)
    place_counts = Counter()
    for place, nomen in iter_nomina(CORPUS):
        if is_imperial_nomen(nomen):
            continue
        by_name[nomen][place] += 1
        if place in coords:
            place_counts[place] += 1

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    regions = load_regions()
    map_overview(rows, coords, place_counts, regions, outdir / 'map1_overview.png')
    map_examples(rows, coords, by_name, regions, outdir / 'map2_examples.png')
    fig_scatter(rows, outdir / 'fig4_dispersion_entropy.png')

    sig = sum(1 for r in rows
              if r.get('morans_z') is not None and r['morans_z'] > 1.96)
    print(f'{len(rows)} names, {sig} spatially clustered, '
          f'{len(place_counts)} located places, {len(regions)} region polygons')
    print(f'written: {outdir}/map1_overview.png, map2_examples.png, '
          f'fig4_dispersion_entropy.png')
    return 0


if __name__ == '__main__':
    sys.exit(main())
