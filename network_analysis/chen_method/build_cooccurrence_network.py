#!/usr/bin/env python3
"""
Object x object co-occurrence within a single inscription.

The deity and nomen networks ask which types share a *place*. This one asks
which types share an *inscription*: the unit is the edcs_id, and two benefaction
objects are tied when one text records both. That is a different question and,
unlike the object x place attempt, it does not saturate. README.md section 3
records why the earlier try failed: 41 categories over 363 places projected to
density 0.945, because statues and temples occur everywhere and so discriminate
nothing. Co-occurrence keeps the type count but drops the place axis, and the
one-mode graph lands at density 0.35.

Louvain fails here as it does elsewhere (Q = 0.07 against a null of 0.19), for
the nested-structure reason in section 4-2. The finding this script is built to
report is the pair-level one: a permutation test that holds the per-type
frequency and the per-inscription type count fixed, and asks which pairs occur
together more often than that baseline allows. Positive and negative deviations
both appear, which is what rules out a pure frequency artefact.

object_type is a category vocabulary, not a controlled one, and its largest
value is `other` (2,833 of 7,590 objects). Leaving those out discards a third of
the corpus; counting them as one node creates a hub that is an artefact of the
extraction. --remap (default) therefore runs each object through
mapping/apply_mapping.py, which resolves 1,758 of the 2,833 by surface form and
yields the two-level category/subtype of OBJECT_TYPE_INVENTORY.md section 7.
--no-remap reproduces the raw object_type behaviour for comparison.

Usage:
    venv/bin/python network_analysis/chen_method/build_cooccurrence_network.py
    venv/bin/python network_analysis/chen_method/build_cooccurrence_network.py --no-remap
    venv/bin/python network_analysis/chen_method/build_cooccurrence_network.py --level subtype
    venv/bin/python network_analysis/chen_method/build_cooccurrence_network.py --province Numidia
"""

import argparse
import json
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

import networkx as nx

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / 'network_analysis' / 'mapping'))

from build_deity_network import CORPUS, louvain  # noqa: E402
from apply_mapping import Classifier, load_map  # noqa: E402

# Placeholders for an object the extraction could not identify. They behave like
# `Unknown deity` in the deity network: treating them as a shared type would tie
# together every inscription whose object is merely illegible.
UNKNOWN_LABELS = {'unknown', 'other', ''}


def iter_inscriptions(corpus: Path, province: str = None):
    """Yield (edcs_id, [object dicts]) one entry per inscription.

    A career file holds many records and a record many persons, but several
    records can carry the same edcs_id — the corpus is keyed by person, not by
    text. Objects are therefore pooled across every record sharing an id, which
    is what makes the unit here an inscription rather than a person.
    """
    pooled = defaultdict(list)
    for path in sorted(corpus.glob('*/*/*_career.json')):
        if province and path.parts[-3].lower() != province.lower().replace(' ', '_'):
            continue
        try:
            data = json.load(open(path, encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            continue
        for rec in data:
            eid = rec.get('edcs_id')
            if not eid:
                continue
            for person in rec.get('persons', []):
                for b in (person.get('benefactions') or []):
                    pooled[eid].extend(b.get('objects') or [])
    return pooled


def label_of(obj, clf, level, drop_unspecified=True):
    """Map one object to its node label, or None if it cannot be placed."""
    if clf is None:
        lab = (obj.get('object_type') or '').strip().lower()
        return lab if lab not in UNKNOWN_LABELS else None

    cat, sub, _how, _nl, _rl = clf.classify(obj.get('object'), obj.get('object_type'))
    if not cat or cat in UNKNOWN_LABELS:
        return None
    if level == 'subtype':
        # A category with no subtype means the text said `opus` or `aedificium`
        # and nothing more. Same situation as the `*.unspecified` subtypes the
        # map assigns to `monumentum` / `votum`: OBJECT_TYPE_INVENTORY.md
        # section 4 classes these as "certainly a monument, but whether tomb,
        # building or statue is not recoverable from the text". That is absence
        # of information, not a type of benefaction, so it cannot be a node --
        # `structure.unspecified -- wall` would only say "some building was
        # mentioned alongside a wall". Dropped unless --keep-unspecified.
        if sub is None or sub.endswith('.unspecified'):
            return None if drop_unspecified else f'{cat}/{cat}.unspecified'
        return f'{cat}/{sub}'
    return cat


def build_sets(pooled, clf, level, drop_unspecified=True):
    """edcs_id -> set of distinct labels. Only inscriptions with >=2 are useful.

    Duplicates within a text are collapsed deliberately: the same object is
    often repeated once per person in the record, so a raw count would measure
    the extraction's redundancy rather than the benefaction.
    """
    sets = {}
    for eid, objs in pooled.items():
        labels = {lab for lab in (label_of(o, clf, level, drop_unspecified)
                                  for o in objs) if lab}
        if labels:
            sets[eid] = labels
    return sets


def cooccurrence(sets, min_weight):
    g = nx.Graph()
    pairs = Counter()
    for labels in sets.values():
        for a, b in combinations(sorted(labels), 2):
            pairs[(a, b)] += 1
    # Sorted insertion: networkx preserves insertion order and
    # null_modularity_onemode's double_edge_swap walks the edge list, so an
    # unsorted Counter makes the null distribution vary between runs.
    for (a, b), w in sorted(pairs.items()):
        if w >= min_weight:
            g.add_edge(a, b, weight=w)
    return g, pairs


def permutation_test(sets, pairs, trials, seed=42):
    """Expected co-occurrence when types are shuffled across inscriptions.

    Both margins are held fixed: every type keeps its number of attestations and
    every inscription keeps its number of distinct types. Only the pairing is
    randomised, so a surviving deviation is about which types co-occur and not
    about how common they are or how verbose the text is. Sampling is without
    replacement within an inscription, matching the distinct-label sets above.
    """
    rng = random.Random(seed)
    # Sorted, not just seeded: `sets` holds Python sets, whose iteration order
    # depends on string hash randomisation and so changes between processes.
    # Seeding the shuffle is not enough if what gets shuffled is already in a
    # different order; without this the z-scores drift run to run.
    items = sorted((eid, sorted(labels)) for eid, labels in sets.items())
    pool = [lab for _eid, labels in items for lab in labels]
    sizes = [len(labels) for _eid, labels in items]

    observed = {k: v for k, v in pairs.items()}
    null = defaultdict(list)
    for _ in range(trials):
        rng.shuffle(pool)
        cur = Counter()
        i = 0
        for size in sizes:
            chunk = set()
            # Walk the shuffled pool until the inscription is refilled with
            # `size` distinct labels, skipping repeats rather than resampling.
            while len(chunk) < size and i < len(pool):
                chunk.add(pool[i])
                i += 1
            for a, b in combinations(sorted(chunk), 2):
                cur[(a, b)] += 1
            if i >= len(pool):
                i = 0
        for key in observed:
            null[key].append(cur.get(key, 0))

    rows = []
    for key, obs in observed.items():
        vals = null[key]
        mean = statistics.mean(vals)
        sd = statistics.pstdev(vals)
        z = (obs - mean) / sd if sd > 0 else float('inf') if obs > mean else 0.0
        rows.append((z, obs, mean, key))
    return sorted(rows, reverse=True)


def null_modularity_onemode(g, trials, seed=42):
    """Louvain Q of degree-preserving rewirings of a one-mode graph.

    build_deity_network.null_modularity rewires the two-mode graph and projects;
    there is no projection step here, so the swap applies to g directly.
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
        _, q = louvain(h, seed=rng.randint(0, 10 ** 6))
        if q == q:
            scores.append(q)
    return scores


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--no-remap', dest='remap', action='store_false',
                    help='use raw object_type instead of the category mapping')
    ap.add_argument('--level', choices=('category', 'subtype'), default='category',
                    help='node granularity when remapping (default: category)')
    ap.add_argument('--min-weight', type=int, default=2,
                    help='drop pairs co-occurring fewer than N times')
    ap.add_argument('--min-pair-obs', type=int, default=8,
                    help='report z only for pairs observed at least N times')
    ap.add_argument('--keep-unspecified', action='store_true',
                    help='keep *.unspecified as nodes (default: drop them; '
                         'they mark missing information, not a benefaction type)')
    ap.add_argument('--province', default=None,
                    help='restrict to one provincia, e.g. "Numidia"')
    ap.add_argument('--permutations', type=int, default=500)
    ap.add_argument('--null-trials', type=int, default=40)
    ap.add_argument('--out', default=str(HERE / 'output'))
    args = ap.parse_args()

    clf = Classifier(load_map()) if args.remap else None

    tag = 'cooc' if args.remap else 'cooc_raw'
    if args.remap and args.level == 'subtype':
        tag += '_subtype'
    if args.keep_unspecified:
        # Own tag, or this run would overwrite the default outputs with a
        # different node set under the same filename.
        tag += '_withunspec'
    if args.province:
        tag += '_' + re.sub(r'\W+', '_', args.province.lower())
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    pooled = iter_inscriptions(CORPUS, args.province)
    sets = build_sets(pooled, clf, args.level, not args.keep_unspecified)
    multi = {k: v for k, v in sets.items() if len(v) > 1}

    with open(outdir / f'report_{tag}.txt', 'w', encoding='utf-8') as fh:
        def emit(s=''):
            print(s)
            fh.write(s + '\n')

        emit(f'province: {args.province or "ALL"}')
        emit(f'labels: {"remapped via object_category_map" if args.remap else "raw object_type"}'
             f'{" (" + args.level + ")" if args.remap else ""}')
        if args.remap:
            emit(f'*.unspecified: {"KEPT as nodes" if args.keep_unspecified else "dropped"}'
                 '  (missing information, not a benefaction type)')
        emit(f'inscriptions (edcs_id): {len(pooled)}  with >=1 usable label: {len(sets)}')
        emit(f'inscriptions with >=2 distinct labels: {len(multi)}'
             f'  ({100 * len(multi) / max(len(pooled), 1):.1f}% of corpus)')

        if len(multi) < 2:
            emit('too few multi-object inscriptions to build a network')
            return 1

        size_dist = Counter(len(v) for v in multi.values())
        emit('label-set size: ' + ', '.join(f'{k}:{v}' for k, v in sorted(size_dist.items())))

        g, pairs = cooccurrence(multi, args.min_weight)
        if g.number_of_edges() == 0:
            emit('no pair survives --min-weight')
            return 1
        emit(f'\n=== co-occurrence graph (min weight {args.min_weight}) ===')
        emit(f'nodes {g.number_of_nodes()}  edges {g.number_of_edges()}  '
             f'density {nx.density(g):.3f}')
        emit('          (object x place projection reached 0.945; see README section 3)')

        comms, q = louvain(g)
        emit(f'Louvain: {len(comms)} communities, modularity Q = {q:.4f}')
        nulls = null_modularity_onemode(g, args.null_trials) if args.null_trials else []
        if nulls:
            mean = statistics.mean(nulls)
            sd = statistics.pstdev(nulls) or float('nan')
            z = (q - mean) / sd if sd == sd and sd > 0 else float('nan')
            emit(f'null (degree-preserving, n={len(nulls)}): '
                 f'{mean:.4f} +/- {sd:.4f}   z = {z:+.2f}')
            if z < 2:
                emit('  Louvain does not beat the null here either (README section 4-2).')
        for c in comms:
            emit('  community: ' + ', '.join(sorted(c)))

        emit(f'\n=== pair permutation test (n={args.permutations}, '
             f'pairs with obs >= {args.min_pair_obs}) ===')
        emit('Margins fixed: per-type frequency and per-inscription type count.')
        rows = [r for r in permutation_test(multi, pairs, args.permutations)
                if r[1] >= args.min_pair_obs]
        emit(f'{"pair":<48}{"obs":>6}{"exp":>9}{"z":>9}')
        for z, obs, mean, (a, b) in rows:
            emit(f'{a + " -- " + b:<48}{obs:>6}{mean:>9.1f}{z:>+9.2f}')

        sig = [r for r in rows if r[0] >= 1.96]
        neg = [r for r in rows if r[0] <= -1.96]
        emit(f'\nsignificant at |z| >= 1.96: {len(sig)} positive, {len(neg)} negative '
             f'(of {len(rows)} tested)')

        nx.write_graphml(g, outdir / f'{tag}.graphml')
        with open(outdir / f'{tag}.json', 'w', encoding='utf-8') as jf:
            json.dump({
                'province': args.province,
                'remap': args.remap,
                'level': args.level if args.remap else None,
                'keep_unspecified': args.keep_unspecified,
                'inscriptions_total': len(pooled),
                'inscriptions_labelled': len(sets),
                'inscriptions_multi': len(multi),
                'objects_total': sum(len(v) for v in pooled.values()),
                'density': nx.density(g),
                'modularity': q,
                'null_mean': statistics.mean(nulls) if nulls else None,
                'pairs': [
                    {'a': a, 'b': b, 'obs': obs, 'expected': mean, 'z': z}
                    for z, obs, mean, (a, b) in rows
                ],
            }, jf, ensure_ascii=False, indent=1)
        emit(f'\nwritten: {outdir}/report_{tag}.txt, {tag}.graphml, {tag}.json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
