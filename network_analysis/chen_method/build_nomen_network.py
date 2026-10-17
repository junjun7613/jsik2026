#!/usr/bin/env python3
"""
Gentilicium (nomen) x place networks following Chen (2023).

Chen, Song. 2023. "Patterns of Integration: A Network Perspective on Popular
Religious Connections in China's Lower Yangzi, 1150-1350." Religions 14(5):577.

Third substitution for Chen's "cult". Benefaction categories were too coarse
(projection density 0.945) and deities too uniform (Q below the degree-
preserving null in five of six configurations) — see README.md.

Gentilicia have a different mechanism behind them. A cult can spread by
imitation to any town, but a nomen spreads by descent and enfranchisement:
veterans settled from one legion, a proconsul's freedmen, a colony founded
from one Italian town all leave clusters of related families in one district.
Sittius is the clearest case here, concentrated around Cirta after Sittius's
followers were settled there in 44 BC. If regional structure exists anywhere
in this corpus, names are where it should be legible.

The data also support it better: 41,387 nomen mentions across 1,621 places
against 4,593 deity attestations across 503, and at the Chen threshold the
nomina/places ratio is 1.37 against Chen's 1.48.

Imperial gentilicia are the complication, and a worse one than for deities.
Iulius, Aurelius, Flavius, Aelius and Septimius are the top names not because
those families were everywhere but because provincials took the emperor's
nomen on enfranchisement — Aurelius above all, after Caracalla's edict of 212
made citizens of nearly everyone. They are the naming equivalent of the
imperial cult: ubiquitous by administrative fiat, carrying no local
information. --exclude-imperial (default) drops them.

Usage:
    venv/bin/python network_analysis/chen_method/build_nomen_network.py
    venv/bin/python network_analysis/chen_method/build_nomen_network.py --include-imperial
    venv/bin/python network_analysis/chen_method/build_nomen_network.py --province Numidia
    venv/bin/python network_analysis/chen_method/build_nomen_network.py --min-nomen-places 5
"""

import argparse
import json
import re
import sys
from pathlib import Path

import networkx as nx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from build_deity_network import (  # noqa: E402
    CORPUS, bridging, build_two_mode, louvain, null_modularity, project,
)

# Gentilicia conferred with citizenship rather than inherited locally. These
# follow the emperor who granted the franchise, so they mark the date of a
# community's enfranchisement, not its regional affiliation, and they appear
# in every town. Aurelius dominates after Caracalla's 212 edict.
IMPERIAL_NOMINA = {
    'iulius', 'iulia', 'claudius', 'claudia', 'flavius', 'flavia',
    'ulpius', 'ulpia', 'aelius', 'aelia', 'aurelius', 'aurelia',
    'septimius', 'septimia', 'valerius', 'valeria',
    'antoninus', 'antonina', 'marcus', 'marcia',
    # Emperors' cognomina, which the extractor sometimes records in the
    # nomen slot. They behave like the conferred gentilicia — ubiquitous and
    # regionally uninformative — and Nerva and Traianus were otherwise the
    # two most dispersed "families" in the corpus.
    'nerva', 'traianus', 'traiana', 'hadrianus', 'hadriana',
    'commodus', 'severus', 'severa', 'caesar', 'augustus', 'augusta',
}

# The corpus carries orthographic variants ("Aurellius" for "Aurelius") that a
# plain set lookup misses, so matching is done on a normalised form.
_DOUBLED = re.compile(r'(.)\1')


def is_imperial_nomen(name: str) -> bool:
    n = (name or '').strip().lower()
    return n in IMPERIAL_NOMINA or _DOUBLED.sub(r'\1', n) in IMPERIAL_NOMINA


def iter_nomina(corpus: Path, province: str = None):
    """
    Yield (place, nomen) for every person reference carrying a gentilicium.

    One attestation per person mention. No attempt is made to resolve the same
    family across inscriptions: Chen's ties are likewise attestations of a cult
    at a place, not counts of shrines, and the two-mode network is unweighted
    so repeats would not change it.
    """
    for path in sorted(corpus.rglob('*_career.json')):
        try:
            data = json.load(open(path, encoding='utf-8'))
        except Exception:
            continue
        for record in (data if isinstance(data, list) else [data]):
            original = record.get('original_data') or {}
            if province and (original.get('province') or '').strip() != province:
                continue
            place = (original.get('place') or original.get('findspot') or '').strip()
            if not place:
                continue
            for person in record.get('persons') or []:
                nomen = (person.get('nomen') or '').strip()
                # Strip editorial brackets left by the transcription, so
                # "[Iul]ius" and "Iulius" are not separate families.
                nomen = re.sub(r'[\[\]()<>?]', '', nomen).strip()
                if len(nomen) > 2:
                    yield place, nomen


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--include-imperial', action='store_true',
                    help='keep imperial gentilicia (default: exclude)')
    ap.add_argument('--province', default=None)
    ap.add_argument('--min-nomen-places', type=int, default=2,
                    help="drop nomina attested at fewer than N places "
                         "(Chen's 56x83 rule is 2)")
    ap.add_argument('--min-place-nomina', type=int, default=2)
    ap.add_argument('--null-trials', type=int, default=20)
    ap.add_argument('--out', default=str(HERE / 'output'))
    args = ap.parse_args()

    raw = list(iter_nomina(CORPUS, args.province))
    pairs = raw if args.include_imperial else [(p, n) for p, n in raw
                                               if not is_imperial_nomen(n)]

    tag = 'nomen_with_imperial' if args.include_imperial else 'nomen'
    if args.province:
        tag += '_' + re.sub(r'\W+', '_', args.province.lower())

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    with open(outdir / f'report_{tag}.txt', 'w', encoding='utf-8') as fh:
        def emit(s=''):
            print(s)
            fh.write(s + '\n')

        emit(f'province: {args.province or "ALL"}')
        emit(f'imperial gentilicia: '
             f'{"included" if args.include_imperial else "EXCLUDED"}')
        emit(f'min_nomen_places={args.min_nomen_places}  '
             f'min_place_nomina={args.min_place_nomina}')
        emit(f'nomen mentions read: {len(raw)}  -> used: {len(pairs)}')

        two = build_two_mode(pairs, args.min_place_nomina, args.min_nomen_places)
        # build_two_mode labels the second mode 'deity'; here those nodes are
        # nomina. The graph logic is identical, so the module is reused rather
        # than copied, and only the reporting renames the mode.
        places = [n for n, d in two.nodes(data=True) if d['kind'] == 'place']
        nomina = [n for n, d in two.nodes(data=True) if d['kind'] == 'deity']
        if not places or not nomina:
            emit('empty network')
            return 1
        dens = two.number_of_edges() / (len(places) * len(nomina))
        emit(f'two-mode: {len(places)} places x {len(nomina)} nomina, '
             f'{two.number_of_edges()} ties, density {dens:.4f}')
        emit(f'          (Chen: 56 places x 83 cults, 378 ties, density 0.081)')

        for side, label in (('deity', 'nomen-nomen'), ('place', 'place-place')):
            proj = project(two, side)
            comms, q = louvain(proj)
            emit(f'\n=== {label} projection ===')
            emit(f'nodes {proj.number_of_nodes()}  edges {proj.number_of_edges()}  '
                 f'density {nx.density(proj):.3f}')
            emit(f'Louvain: {len(comms)} communities, modularity Q = {q:.4f}')
            if q >= 0.30:
                emit('  Q >= 0.30: clear community structure.')
            elif q < 0.20:
                emit('  Q < 0.20: no meaningful community structure.')

            nulls = (null_modularity(two, side, args.null_trials)
                     if args.null_trials else [])
            if nulls:
                mean = sum(nulls) / len(nulls)
                sd = (sum((x - mean) ** 2 for x in nulls) / len(nulls)) ** 0.5
                z = (q - mean) / sd if sd else float('nan')
                emit(f'null model: Q = {mean:.4f} +/- {sd:.4f} over {len(nulls)} '
                     f'rewirings, z = {z:+.2f}')
                emit('  -> structure exceeds degree-driven expectation' if z > 2
                     else '  -> NOT clearly above what degree alone predicts')

            for i, c in enumerate(comms[:10], 1):
                members = sorted(c, key=lambda n: -proj.degree(n, weight='weight'))
                emit(f'  cluster {i} (n={len(c)}): '
                     + ', '.join(str(m)[:26] for m in members[:8])
                     + ('...' if len(members) > 8 else ''))

            emit(f'  bridging (clusters spanned, weighted degree):')
            for n, spans, deg in bridging(proj, comms)[:10]:
                emit(f'    {str(n)[:42]:44} spans {spans}  deg {deg}')

            h = nx.relabel_nodes(proj, {n: str(n) for n in proj.nodes()})
            nx.write_graphml(h, outdir / f'{tag}_{side}_projection.graphml')

        h = nx.relabel_nodes(two, {n: f'{n[0]}:{n[1]}' for n in two.nodes()})
        nx.write_graphml(h, outdir / f'{tag}_two_mode.graphml')

    print(f'\nwritten: {outdir}/report_{tag}.txt and *.graphml')
    return 0


if __name__ == '__main__':
    sys.exit(main())
