#!/usr/bin/env python3
"""
Deity x place networks following Chen (2023).

Chen, Song. 2023. "Patterns of Integration: A Network Perspective on Popular
Religious Connections in China's Lower Yangzi, 1150-1350." Religions 14(5):577.

This is the variant build_network.py pointed to. Chen's "cults" are named
deities, not categories of offering, and that distinction decided the earlier
run: with 41 object categories over 363 places the one-mode projection reached
density 0.945 and Louvain had nothing to partition (see README.md section 3).

Deities restore the shape Chen relies on. 500 distinct divinity_type values
attach to 503 places, and after dropping deities attested at a single place
the two-mode density is 0.043 against Chen's 0.081 — sparse enough for
community structure to be detectable if it exists.

Deified emperors are the complication. The corpus marks Nerva, Traianus and
Hadrianus as divinity=true, and they are the three most frequent values. They
belong to the imperial cult, which was promoted uniformly across the provinces,
so they appear nearly everywhere and connect every place to every other. That
is the same saturation problem in a different guise, and it is also why
FEASIBILITY.md requires an imperial filter for the career-transition network.
--exclude-imperial (default) drops them; --include-imperial keeps them so the
effect can be inspected.

Usage:
    venv/bin/python network_analysis/chen_method/build_deity_network.py
    venv/bin/python network_analysis/chen_method/build_deity_network.py --include-imperial
    venv/bin/python network_analysis/chen_method/build_deity_network.py --min-deity-places 3
"""

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
CORPUS = REPO / 'pipeline' / 'provenance' / 'validated_career_graphs' / 'claude'

# Imperial names and titles that mark a deified emperor or member of the
# imperial house. Matched case-insensitively against the whole divinity_type,
# so "Antoninus Pius" and "Marcus Antoninus" are both caught, while the god
# Mercurius or the personification Victoria are not.
IMPERIAL_TOKENS = {
    'augustus', 'augusta', 'caesar', 'nerva', 'traianus', 'trajan', 'hadrianus',
    'hadrian', 'antoninus', 'pius', 'commodus', 'severus', 'septimius',
    'caracalla', 'geta', 'elagabalus', 'alexander', 'maximinus', 'gordianus',
    'philippus', 'decius', 'valerianus', 'gallienus', 'claudius', 'aurelianus',
    'probus', 'diocletianus', 'maximianus', 'constantinus', 'constantius',
    'licinius', 'galerius', 'vespasianus', 'titus', 'domitianus', 'nero',
    'tiberius', 'vitellius', 'otho', 'galba', 'marcus', 'lucius', 'verus',
    'faustina', 'sabina', 'plotina', 'matidia', 'iulia', 'julia', 'domna',
    'mamaea', 'helena', 'divus', 'diva', 'imperator',
}

IMPERIAL_RE = re.compile(
    r'\b(' + '|'.join(sorted(IMPERIAL_TOKENS, key=len, reverse=True)) + r')\b',
    re.IGNORECASE)


def is_imperial(name: str) -> bool:
    return bool(IMPERIAL_RE.search(name or ''))


# ── Corpus reading ────────────────────────────────────────────────────────────

def iter_deities(corpus: Path, province: str = None):
    """
    Yield (place, deity) for every person flagged divinity=true.

    Deities are recorded as person references with divinity=true and a
    divinity_type naming the god, rather than as objects of a benefaction, so
    the attestation is read from the person list (see FEASIBILITY.md section 4).

    province restricts to one provincia. Chen's region is a single cultural
    area of 56 places; pooling all of North Africa may average away whatever
    sub-regional variation exists, so the provinces can be run separately.
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
                if not person.get('divinity'):
                    continue
                deity = (person.get('divinity_type') or '').strip()
                # "Unknown deity" records that a god was named but could not be
                # identified. Treating it as a cult would tie together every
                # place with an illegible theonym.
                if deity and deity.lower() not in ('unknown deity', 'unknown',
                                                   'deus', 'dea', 'unknown god'):
                    yield place, deity


# ── Two-mode construction (Chen's step 1) ─────────────────────────────────────

def build_two_mode(pairs, min_place_deities: int, min_deity_places: int):
    """
    Undirected, unweighted place x deity network.

    Unweighted follows Chen and matters here too: Carthago yields far more
    inscriptions than a small town, so counting attestations would make the
    projection a map of excavation intensity rather than of cult distribution.

    min_deity_places defaults to 2 for Chen's reason — a deity attested at one
    place cannot connect anything. Verified against his 56x83 edge list.
    """
    attested = defaultdict(set)
    for place, deity in pairs:
        attested[place].add(deity)

    deity_places = defaultdict(set)
    for place, deities in attested.items():
        for deity in deities:
            deity_places[deity].add(place)

    keep_deity = {d for d, ps in deity_places.items() if len(ps) >= min_deity_places}
    keep_place = {p for p, ds in attested.items()
                  if len(ds & keep_deity) >= min_place_deities}

    g = nx.Graph()
    for place in keep_place:
        g.add_node(('place', place), kind='place', label=place)
    for deity in keep_deity:
        g.add_node(('deity', deity), kind='deity', label=deity)
    for place in keep_place:
        for deity in attested[place] & keep_deity:
            g.add_edge(('place', place), ('deity', deity))
    return g


def project(g: nx.Graph, side: str) -> nx.Graph:
    """Weighted one-mode projection; weight = shared counterparts (Chen Fig. 7)."""
    nodes = [n for n, d in g.nodes(data=True) if d['kind'] == side]
    p = nx.bipartite.weighted_projected_graph(g, nodes)
    return nx.relabel_nodes(p, {n: n[1] for n in p.nodes()})


def louvain(g: nx.Graph, seed: int = 42):
    if g.number_of_edges() == 0:
        return [], float('nan')
    comms = nx.community.louvain_communities(g, weight='weight', seed=seed)
    comms = sorted(comms, key=len, reverse=True)
    return comms, nx.community.modularity(g, comms, weight='weight')


def null_modularity(g: nx.Graph, side: str, trials: int, seed: int = 42):
    """
    Modularity of degree-preserving rewirings.

    Chen works from hand-curated gazetteer entries; these ties come from LLM
    extraction over an unevenly excavated corpus where a few large sites supply
    most attestations, so some apparent clustering is expected from degree
    alone. Rewiring holds the degree sequence fixed and destroys everything else.
    """
    rng = random.Random(seed)
    scores = []
    for _ in range(trials):
        h = g.copy()
        try:
            nx.double_edge_swap(h, nswap=h.number_of_edges() * 2,
                                max_tries=h.number_of_edges() * 100,
                                seed=rng.randint(0, 10 ** 6))
        except (nx.NetworkXError, nx.NetworkXAlgorithmError):
            continue
        _, q = louvain(project(h, side), seed=rng.randint(0, 10 ** 6))
        if q == q:
            scores.append(q)
    return scores


def bridging(g: nx.Graph, comms) -> list:
    """Chen's "cults connecting clusters": nodes whose neighbours span clusters."""
    member = {n: i for i, c in enumerate(comms) for n in c}
    out = []
    for n in g.nodes():
        spans = {member[m] for m in g.neighbors(n) if m in member}
        out.append((n, len(spans), g.degree(n, weight='weight')))
    return sorted(out, key=lambda x: (-x[1], -x[2]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--include-imperial', action='store_true',
                    help='keep deified emperors (default: exclude)')
    ap.add_argument('--min-deity-places', type=int, default=2,
                    help="drop deities attested at fewer than N places "
                         "(Chen's 56x83 rule is 2)")
    ap.add_argument('--min-place-deities', type=int, default=2,
                    help='drop places attesting fewer than N deities')
    ap.add_argument('--province', default=None,
                    help='restrict to one provincia, e.g. "Numidia"')
    ap.add_argument('--null-trials', type=int, default=20)
    ap.add_argument('--out', default=str(HERE / 'output'))
    args = ap.parse_args()

    raw = list(iter_deities(CORPUS, args.province))
    imperial = {d for _, d in raw if is_imperial(d)}
    if args.include_imperial:
        pairs = raw
    else:
        pairs = [(p, d) for p, d in raw if d not in imperial]

    tag = 'deity_with_imperial' if args.include_imperial else 'deity'
    if args.province:
        tag += '_' + re.sub(r'\W+', '_', args.province.lower())
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    with open(outdir / f'report_{tag}.txt', 'w', encoding='utf-8') as fh:
        def emit(s=''):
            print(s)
            fh.write(s + '\n')

        emit(f'province: {args.province or "ALL"}')
        emit(f'imperial deities: {"included" if args.include_imperial else "EXCLUDED"}'
             f'  ({len(imperial)} distinct names matched)')
        emit(f'min_deity_places={args.min_deity_places}  '
             f'min_place_deities={args.min_place_deities}')
        emit(f'deity attestations read: {len(raw)}  -> used: {len(pairs)}')

        two = build_two_mode(pairs, args.min_place_deities, args.min_deity_places)
        places = [n for n, d in two.nodes(data=True) if d['kind'] == 'place']
        deities = [n for n, d in two.nodes(data=True) if d['kind'] == 'deity']
        if not places or not deities:
            emit('empty network')
            return 1
        dens = two.number_of_edges() / (len(places) * len(deities))
        emit(f'two-mode: {len(places)} places x {len(deities)} deities, '
             f'{two.number_of_edges()} ties, density {dens:.3f}')
        emit(f'          (Chen: 56 places x 83 cults, 378 ties, density 0.081)')

        for side, label in (('deity', 'deity-deity'), ('place', 'place-place')):
            proj = project(two, side)
            comms, q = louvain(proj)
            emit(f'\n=== {label} projection ===')
            emit(f'nodes {proj.number_of_nodes()}  edges {proj.number_of_edges()}  '
                 f'density {nx.density(proj):.3f}')
            emit(f'Louvain: {len(comms)} communities, modularity Q = {q:.4f}')
            if q < 0.20:
                emit('  Q < 0.20: no meaningful community structure.')

            nulls = null_modularity(two, side, args.null_trials) if args.null_trials else []
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
                     + ', '.join(str(m)[:30] for m in members[:8])
                     + ('...' if len(members) > 8 else ''))

            emit(f'  bridging {side}s (clusters spanned, weighted degree):')
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
