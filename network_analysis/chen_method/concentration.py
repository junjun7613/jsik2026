#!/usr/bin/env python3
"""
Geographic concentration of gentilicia — the alternative to community detection.

Chen's Louvain step fails on this corpus, and the nomen run showed why: regional
signal exists (Sittius clusters on Cirta, Gabinius on Dougga) but modularity
cannot see it, because the place x name matrix is nested rather than modular.
Carthago attests 448 nomina and a small town two or three, almost always a
subset — so every partition leaves the big towns joined to everything, and Q
stays low however the network is cut (see README.md sections 1-0 and 4-2).

Nestedness defeats partitioning but not concentration. This script asks of each
name "where is it, and is that somewhere in particular?" instead of "which group
does it belong to":

  entropy     how evenly a name spreads over the places attesting it
  centroid    the mean position of its attestations, weighted by count
  dispersion  mean distance from that centroid, in km
  Moran's I   whether attestation counts cluster in space beyond chance

Entropy and dispersion answer different questions and disagree usefully. A name
in four towns 20 km apart and one in four towns 600 km apart have the same
entropy; only dispersion separates them. Entropy is computed for every name,
dispersion only where coordinates are known (993 of 1,621 places).

Usage:
    venv/bin/python network_analysis/chen_method/concentration.py
    venv/bin/python network_analysis/chen_method/concentration.py --min-count 20
    venv/bin/python network_analysis/chen_method/concentration.py --province Numidia
"""

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from build_nomen_network import CORPUS, is_imperial_nomen, iter_nomina  # noqa: E402

# The corpus is North African but carries a tail of inscriptions from elsewhere
# (Hispania, Italy, Asia Minor). Left in, a single Roman attestation drags a
# name's centroid across the Mediterranean and inflates its dispersion.
AFRICA_BOX = dict(lat=(23.0, 38.5), lon=(-10.0, 26.0))


def in_africa(lat, lon):
    return (AFRICA_BOX['lat'][0] <= lat <= AFRICA_BOX['lat'][1]
            and AFRICA_BOX['lon'][0] <= lon <= AFRICA_BOX['lon'][1])


def load_coords(corpus: Path, province: str = None) -> dict:
    """place -> (lat, lon), restricted to the North African box."""
    coords = {}
    for path in sorted(corpus.rglob('*_career.json')):
        try:
            data = json.load(open(path, encoding='utf-8'))
        except Exception:
            continue
        for record in (data if isinstance(data, list) else [data]):
            od = record.get('original_data') or {}
            if province and (od.get('province') or '').strip() != province:
                continue
            place = (od.get('place') or '').strip()
            if not place or place in coords:
                continue
            try:
                lat, lon = float(od.get('latitude')), float(od.get('longitude'))
            except (TypeError, ValueError):
                continue
            if in_africa(lat, lon):
                coords[place] = (lat, lon)
    return coords


def haversine(a, b) -> float:
    """Great-circle distance in km."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def normalised_entropy(counts) -> float:
    """
    Shannon entropy over places, divided by its maximum.

    0 = every attestation in one place, 1 = spread evenly over the places where
    the name occurs. Normalising makes names attested at different numbers of
    places comparable; without it a name in 50 towns always scores above a name
    in 5, however lopsided its distribution.
    """
    total = sum(counts)
    if total == 0 or len(counts) <= 1:
        # A name in a single place is maximally concentrated by definition.
        # The score is real but says nothing a reader could not read off the
        # place count, so the report marks these rather than ranking them.
        return 0.0
    h = -sum((c / total) * math.log(c / total) for c in counts if c)
    return h / math.log(len(counts))


def weighted_centroid(place_counts, coords):
    """Attestation-weighted mean position, and mean km from it."""
    pts = [(coords[p], n) for p, n in place_counts.items() if p in coords]
    if not pts:
        return None, None, 0
    w = sum(n for _, n in pts)
    lat = sum(c[0] * n for c, n in pts) / w
    lon = sum(c[1] * n for c, n in pts) / w
    disp = sum(haversine((lat, lon), c) * n for c, n in pts) / w
    return (lat, lon), disp, w


def morans_i(values: dict, coords: dict, bandwidth_km: float = 75.0):
    """
    Moran's I on per-place attestation counts, with a distance-band weight.

    Entropy says a name is uneven; it does not say the places it favours are
    near each other. Moran's I does: positive means places with similar counts
    are spatially adjacent, which is what "regional" means. Returns (I, z)
    under the normality assumption; z > 1.96 is the usual 5% threshold.

    values must cover every place in the study area, scoring 0 where the name
    is absent. Passing only the places that attest it asks whether the name is
    uneven *among the towns that already have it* — a much weaker question that
    discards the evidence absence carries. For Sittius the difference is
    z = 0.8 against z = 8.9.
    """
    places = [p for p in values if p in coords]
    n = len(places)
    if n < 8:
        return None, None
    x = np.array([values[p] for p in places], dtype=float)
    z = x - x.mean()
    if not z.any():
        return None, None

    w = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i != j and haversine(coords[places[i]], coords[places[j]]) <= bandwidth_km:
                w[i, j] = 1.0
    s0 = w.sum()
    if s0 == 0:
        return None, None

    num = float(z @ w @ z)
    I = (n / s0) * (num / float(z @ z))
    e_i = -1.0 / (n - 1)

    s1 = 0.5 * ((w + w.T) ** 2).sum()
    s2 = ((w.sum(axis=1) + w.sum(axis=0)) ** 2).sum()
    b2 = (n * (z ** 4).sum()) / ((z ** 2).sum() ** 2)
    var = ((n * ((n ** 2 - 3 * n + 3) * s1 - n * s2 + 3 * s0 ** 2)
            - b2 * ((n ** 2 - n) * s1 - 2 * n * s2 + 6 * s0 ** 2))
           / ((n - 1) * (n - 2) * (n - 3) * s0 ** 2)) - e_i ** 2
    if var <= 0:
        return I, None
    return I, (I - e_i) / math.sqrt(var)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--min-count', type=int, default=30,
                    help='ignore names with fewer attestations')
    ap.add_argument('--province', default=None)
    ap.add_argument('--include-imperial', action='store_true')
    ap.add_argument('--bandwidth', type=float, default=75.0,
                    help="Moran's I neighbour distance in km")
    ap.add_argument('--top', type=int, default=20)
    ap.add_argument('--out', default=str(HERE / 'output'))
    args = ap.parse_args()

    raw = list(iter_nomina(CORPUS, args.province))
    if not args.include_imperial:
        raw = [(p, n) for p, n in raw if not is_imperial_nomen(n)]
    coords = load_coords(CORPUS, args.province)

    by_name = defaultdict(Counter)
    for place, nomen in raw:
        by_name[nomen][place] += 1

    # The study area for Moran's I: every located place attesting any nomen.
    # A name's absence from one of these is evidence about where it is not.
    study_area = sorted({p for p, _ in raw} & set(coords))

    rows = []
    for nomen, pc in by_name.items():
        total = sum(pc.values())
        if total < args.min_count:
            continue
        h = normalised_entropy(list(pc.values()))
        centroid, disp, located = weighted_centroid(pc, coords)
        I, z = morans_i({p: pc.get(p, 0) for p in study_area},
                        coords, args.bandwidth)
        top_place, top_n = pc.most_common(1)[0]
        rows.append({
            'nomen': nomen, 'total': total, 'places': len(pc),
            'entropy': h, 'dispersion_km': disp, 'located': located,
            'top_place': top_place, 'top_share': top_n / total,
            'morans_i': I, 'morans_z': z,
            'centroid': centroid,
        })

    rows.sort(key=lambda r: r['entropy'])
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    tag = 'concentration' + (f'_{args.province.lower().replace(" ", "_")}'
                             if args.province else '')

    with open(outdir / f'{tag}.txt', 'w', encoding='utf-8') as fh:
        def emit(s=''):
            print(s)
            fh.write(s + '\n')

        emit(f'province: {args.province or "ALL"}   '
             f'imperial: {"included" if args.include_imperial else "EXCLUDED"}')
        emit(f'min_count={args.min_count}  Moran bandwidth={args.bandwidth:g} km')
        emit(f'names analysed: {len(rows)}   places with coordinates: {len(coords)}')
        emit()
        emit('H = normalised entropy (0 = one place, 1 = even)')
        emit('disp = mean km from the attestation-weighted centroid')
        emit("I, z = Moran's I on per-place counts; z > 1.96 is clustered at 5%")
        emit()

        hdr = (f'{"nomen":<22}{"n":>6}{"places":>7}{"H":>7}{"disp":>8}'
               f'{"I":>7}{"z":>7}  top place')
        emit('=== MOST CONCENTRATED ===')
        emit(hdr)
        for r in rows[:args.top]:
            emit(f'{r["nomen"][:21]:<22}{r["total"]:>6}{r["places"]:>7}'
                 f'{r["entropy"]:>7.3f}'
                 f'{(f"{r['dispersion_km']:.0f}" if r['dispersion_km'] else "-"):>8}'
                 f'{(f"{r['morans_i']:.2f}" if r['morans_i'] is not None else "-"):>7}'
                 f'{(f"{r['morans_z']:.1f}" if r['morans_z'] is not None else "-"):>7}'
                 f'  {r["top_place"].split("/")[0].strip()[:26]} '
                 f'({r["top_share"]*100:.0f}%)')

        emit()
        emit('=== MOST DISPERSED ===')
        emit(hdr)
        for r in rows[-args.top:]:
            emit(f'{r["nomen"][:21]:<22}{r["total"]:>6}{r["places"]:>7}'
                 f'{r["entropy"]:>7.3f}'
                 f'{(f"{r['dispersion_km']:.0f}" if r['dispersion_km'] else "-"):>8}'
                 f'{(f"{r['morans_i']:.2f}" if r['morans_i'] is not None else "-"):>7}'
                 f'{(f"{r['morans_z']:.1f}" if r['morans_z'] is not None else "-"):>7}'
                 f'  {r["top_place"].split("/")[0].strip()[:26]} '
                 f'({r["top_share"]*100:.0f}%)')

        sig = [r for r in rows if r['morans_z'] is not None and r['morans_z'] > 1.96]
        emit()
        emit(f"=== SPATIALLY CLUSTERED (Moran's z > 1.96): "
             f"{len(sig)} of {sum(1 for r in rows if r['morans_z'] is not None)} testable ===")
        for r in sorted(sig, key=lambda r: -r['morans_z'])[:args.top]:
            emit(f'{r["nomen"][:21]:<22}{r["total"]:>6}{r["places"]:>7}'
                 f'{r["entropy"]:>7.3f}'
                 f'{(f"{r['dispersion_km']:.0f}" if r['dispersion_km'] else "-"):>8}'
                 f'{r["morans_i"]:>7.2f}{r["morans_z"]:>7.1f}'
                 f'  {r["top_place"].split("/")[0].strip()[:26]} '
                 f'({r["top_share"]*100:.0f}%)')

    with open(outdir / f'{tag}.json', 'w', encoding='utf-8') as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)

    print(f'\nwritten: {outdir}/{tag}.txt and .json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
