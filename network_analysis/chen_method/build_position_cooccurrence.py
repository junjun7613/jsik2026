#!/usr/bin/env python3
"""
Position x position co-occurrence between DIFFERENT people in one inscription.

build_cooccurrence_network.py asks which benefaction types share a text. This
asks which offices do — but with a restriction that decides the whole result:
the two positions must belong to two different people. A single person's
career_path is a cursus, an ordered sequence ("aedilis, then duovir"), and
flattening it into an undirected tie would throw away the `order` field and
answer a different question badly. FEASIBILITY.md already reserves that one for
a directed career-transition network; this script deliberately does not touch
it. Of the inscriptions carrying two or more positions, 1,170 are one person's
cursus and 659 span several people — only the latter are used here.

What survives is a question about who appears alongside whom: a municipal
patron named next to a flamen, a legate next to a centurion. That is a claim
about the composition of the record, not about any individual's advancement.

Imperial titulature has to go first, and it is the bulk of the data. `consul`,
`imperator`, `tribunicia potestas` and `pater patriae` are the four most common
values in the corpus, because every dedication to an emperor lists his styling
in full. They are not offices anyone competed for, and keeping them would tie
every imperial dedication to every other — the same saturation that sank the
object x place attempt (README section 3) and that forces the imperial filter in
build_deity_network.py and FEASIBILITY.md. Two filters are applied: the person
is dropped if they are an emperor, and the position is dropped if it is pure
titulature. Together these remove 14,548 person-records and leave 827 usable
inscriptions.

Usage:
    venv/bin/python network_analysis/chen_method/build_position_cooccurrence.py
    venv/bin/python network_analysis/chen_method/build_position_cooccurrence.py --level type
    venv/bin/python network_analysis/chen_method/build_position_cooccurrence.py --include-imperial
    venv/bin/python network_analysis/chen_method/build_position_cooccurrence.py --province Numidia
"""

import argparse
import json
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from build_deity_network import CORPUS, is_imperial, louvain  # noqa: E402
from build_cooccurrence_network import null_modularity_onemode  # noqa: E402

# Imperial styling rather than an office: victory cognomina, the tribunician
# power, and the honorifics that accompany them. `consul` is NOT here — ordinary
# senators held it, and dropping it would delete a real municipal career step.
# Emperors reach it through the is_imperial person filter instead.
TITULATURE = {
    'imperator', 'augustus', 'augusta', 'caesar', 'pater patriae',
    'mater castrorum', 'tribunicia potestas', 'pontifex maximus',
    'nobilissimus caesar', 'princeps iuventutis', 'princeps senatus',
    'germanicus', 'parthicus', 'britannicus', 'dacicus', 'sarmaticus',
    'armeniacus', 'adiabenicus', 'medicus parthicus', 'maximus', 'invictus',
    'pius felix', 'divus', 'diva', 'restitutor', 'conservator', 'propagator',
}


def iter_inscription_positions(corpus: Path, province=None, include_imperial=False,
                               level='position'):
    """edcs_id -> {person_id: {positions}}, pooled across records sharing an id.

    Keyed by person inside the inscription so the caller can tell a single
    cursus from several people's offices; that distinction is the point of this
    script. Records are pooled by edcs_id for the same reason as in
    build_cooccurrence_network: the corpus is keyed by person, not by text.
    """
    pooled = defaultdict(lambda: defaultdict(set))
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
                status = (person.get('social_status') or '').lower()
                name = person.get('person_name') or ''
                if not include_imperial and (is_imperial(name)
                                             or 'emperor' in status
                                             or 'empress' in status):
                    continue
                # person_id is unique only within a record, so pair it with the
                # person's name to keep two different people apart when several
                # records share one edcs_id.
                key = (person.get('person_id'), name)
                for step in (person.get('career_path') or []):
                    if level == 'type':
                        lab = (step.get('position_type') or '').strip().lower()
                    else:
                        lab = (step.get('position_abstract')
                               or step.get('position_normalized') or '').strip().lower()
                    if not lab or lab in ('', 'other', 'unknown'):
                        continue
                    if (not include_imperial and level == 'position'
                            and lab in TITULATURE):
                        continue
                    pooled[eid][key].add(lab)
    return pooled


def build_sets(pooled, cross_person=True):
    """edcs_id -> set of positions, keeping only usable inscriptions.

    With cross_person (the default) an inscription counts only if two or more
    *different people* hold positions in it, and its label set is the union of
    theirs. A text recording one man's cursus contributes nothing, by design.

    The union is for the node set and the permutation margins only. It is NOT
    enough on its own: `consul` and `praetor` both appear in the union whenever
    one senator held both, so counting pairs off the union would smuggle the
    cursus back in through the inscriptions that also happen to name a second
    person. cross_person_pairs() below does the actual pair counting.
    """
    sets = {}
    for eid, by_person in pooled.items():
        if cross_person:
            if len(by_person) < 2:
                continue
        labels = set().union(*by_person.values()) if by_person else set()
        if labels:
            sets[eid] = labels
    return sets


def cross_person_pairs(pooled, sets):
    """Count a pair only when the two positions sit on two different people.

    Drops `a -- b` whenever one person holds both, even if the inscription is
    kept for other pairs: that combination is a cursus step, and this script
    exists to keep cursus structure out. Measured effect is large where it
    matters — `consul -- praetor` loses 12 of 27, `aedilis -- duovir` 8 of 11 —
    and nil for pairs that were never a career sequence (`centurio -- miles`
    loses 1 of 48).
    """
    pairs = Counter()
    for eid in sets:
        people = list(pooled[eid].values())
        # Collected per inscription, then counted once: one text naming the
        # same office-pair across several person-combinations must not count
        # it repeatedly. The unit of observation is the inscription, as
        # everywhere else in this directory.
        seen = set()
        for i in range(len(people)):
            for j in range(i + 1, len(people)):
                for a in people[i]:
                    for b in people[j]:
                        if a != b:
                            seen.add(tuple(sorted((a, b))))
        for key in seen:
            pairs[key] += 1
    return pairs


def cross_person_permutation(pooled, sets, observed, trials, seed=42):
    """Expected cross-person co-occurrence under a reshuffle of positions.

    build_cooccurrence_network.permutation_test cannot be reused here: it works
    from one label set per inscription and knows nothing about who held what, so
    its null would count cursus pairs that the observed side excludes, inflating
    every expected value and deflating every z.

    This keeps the person structure fixed — the same inscriptions, each with the
    same number of people, each person holding the same number of positions —
    and only reassigns which positions land on which person. Pairs are then
    counted with the same cross-person rule as the observed side, so the two are
    measured the same way.
    """
    rng = random.Random(seed)
    # Shape: per inscription, the list of per-person position counts.
    shape = []
    pool = []
    for eid in sorted(sets):
        # Sorted by content, not by dict order: `pooled[eid]` is keyed by
        # (person_id, name) and its values are sets, so both the person order
        # and the pool order would otherwise vary with hash randomisation and
        # the z-scores would drift between runs.
        people = sorted((sorted(v) for v in pooled[eid].values()),
                        key=lambda p: (len(p), p))
        shape.append((eid, [len(p) for p in people]))
        for p in people:
            pool.extend(p)

    null = defaultdict(list)
    for _ in range(trials):
        rng.shuffle(pool)
        cur = Counter()
        i = 0
        for _eid, sizes in shape:
            people = []
            for size in sizes:
                chunk = set()
                while len(chunk) < size and i < len(pool):
                    chunk.add(pool[i])
                    i += 1
                people.append(chunk)
                if i >= len(pool):
                    i = 0
            seen = set()
            for a_i in range(len(people)):
                for b_i in range(a_i + 1, len(people)):
                    for a in people[a_i]:
                        for b in people[b_i]:
                            if a != b:
                                seen.add(tuple(sorted((a, b))))
            for key in seen:
                cur[key] += 1
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--level', choices=('position', 'type'), default='position',
                    help='position_abstract (default) or the coarser position_type')
    ap.add_argument('--include-imperial', action='store_true',
                    help='keep emperors and their titulature (default: drop)')
    ap.add_argument('--any-person', action='store_true',
                    help='also count single-cursus inscriptions (default: require '
                         'two different people; a cursus is ordered, not a co-occurrence)')
    ap.add_argument('--min-weight', type=int, default=2)
    ap.add_argument('--min-pair-obs', type=int, default=8)
    ap.add_argument('--province', default=None)
    ap.add_argument('--permutations', type=int, default=500)
    ap.add_argument('--null-trials', type=int, default=40)
    ap.add_argument('--out', default=str(HERE / 'output'))
    args = ap.parse_args()

    tag = 'pos' if args.level == 'position' else 'pos_type'
    if args.include_imperial:
        tag += '_with_imperial'
    if args.any_person:
        tag += '_anyperson'
    if args.province:
        tag += '_' + re.sub(r'\W+', '_', args.province.lower())
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    pooled = iter_inscription_positions(CORPUS, args.province,
                                        args.include_imperial, args.level)
    sets = build_sets(pooled, cross_person=not args.any_person)
    multi = {k: v for k, v in sets.items() if len(v) > 1}

    with open(outdir / f'report_{tag}.txt', 'w', encoding='utf-8') as fh:
        def emit(s=''):
            print(s)
            fh.write(s + '\n')

        emit(f'province: {args.province or "ALL"}')
        emit(f'label: {args.level}')
        emit(f'imperial: {"INCLUDED" if args.include_imperial else "excluded "
                          "(emperors as persons, and pure titulature)"}')
        emit(f'unit: {"any inscription with positions" if args.any_person else
                      "inscriptions where 2+ DIFFERENT people hold positions"}')
        n_cursus = sum(1 for v in pooled.values() if len(v) == 1)
        emit(f'inscriptions with positions: {len(pooled)}'
             f'  (single-cursus, excluded: {n_cursus})')
        emit(f'usable: {len(sets)}   with >=2 distinct positions: {len(multi)}')

        if len(multi) < 2:
            emit('too few inscriptions to build a network')
            return 1

        size_dist = Counter(len(v) for v in multi.values())
        emit('label-set size: ' + ', '.join(f'{k}:{v}' for k, v in sorted(size_dist.items())))

        pairs = cross_person_pairs(pooled, multi)
        g = nx.Graph()
        # Sorted insertion: networkx preserves insertion order, and
        # double_edge_swap walks the edge list, so an unsorted Counter would
        # give a different null distribution on every run.
        for (a, b), w in sorted(pairs.items()):
            if w >= args.min_weight:
                g.add_edge(a, b, weight=w)
        if g.number_of_edges() == 0:
            emit('no pair survives --min-weight')
            return 1
        emit(f'\n=== co-occurrence graph (min weight {args.min_weight}) ===')
        emit(f'nodes {g.number_of_nodes()}  edges {g.number_of_edges()}  '
             f'density {nx.density(g):.3f}')

        comms, q = louvain(g)
        emit(f'Louvain: {len(comms)} communities, modularity Q = {q:.4f}')
        nulls = null_modularity_onemode(g, args.null_trials) if args.null_trials else []
        if nulls:
            mean = statistics.mean(nulls)
            sd = statistics.pstdev(nulls)
            z = (q - mean) / sd if sd > 0 else float('nan')
            emit(f'null (degree-preserving, n={len(nulls)}): '
                 f'{mean:.4f} +/- {sd:.4f}   z = {z:+.2f}')
        for c in comms:
            emit('  community: ' + ', '.join(sorted(c)))

        emit(f'\n=== pair permutation test (n={args.permutations}, '
             f'pairs with obs >= {args.min_pair_obs}) ===')
        rows = [r for r in cross_person_permutation(
                    pooled, multi, dict(pairs), args.permutations)
                if r[1] >= args.min_pair_obs]
        emit(f'{"pair":<52}{"obs":>6}{"exp":>9}{"z":>9}')
        for z, obs, mean, (a, b) in rows:
            emit(f'{a + " -- " + b:<52}{obs:>6}{mean:>9.1f}{z:>+9.2f}')

        sig = [r for r in rows if r[0] >= 1.96]
        neg = [r for r in rows if r[0] <= -1.96]
        emit(f'\nsignificant at |z| >= 1.96: {len(sig)} positive, {len(neg)} negative '
             f'(of {len(rows)} tested)')

        nx.write_graphml(g, outdir / f'{tag}.graphml')
        with open(outdir / f'{tag}.json', 'w', encoding='utf-8') as jf:
            json.dump({
                'province': args.province,
                'level': args.level,
                'include_imperial': args.include_imperial,
                'cross_person_only': not args.any_person,
                'inscriptions_total': len(pooled),
                'inscriptions_labelled': len(sets),
                'inscriptions_multi': len(multi),
                'density': nx.density(g),
                'modularity': q,
                'null_mean': statistics.mean(nulls) if nulls else None,
                'pairs': [{'a': a, 'b': b, 'obs': obs, 'expected': mean, 'z': z}
                          for z, obs, mean, (a, b) in rows],
            }, jf, ensure_ascii=False, indent=1)
        emit(f'\nwritten: {outdir}/report_{tag}.txt, {tag}.graphml, {tag}.json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
