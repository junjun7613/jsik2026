#!/usr/bin/env python3
"""
Career-step adjacency within one person's cursus (README section 1-5).

The three co-occurrence scripts in this directory all collapse ~700 years into
one network and have no internal notion of time. This one does not, and that is
the point: a cursus carries *relative* chronology inside a single life. The
`order` field says which post came next, so the sequence is usable whether or
not the inscription carries an absolute date — 1,655 careers qualify, while only
604 of them (36%) are dated at all.

Edges are between steps that are ADJACENT in the sequence, and they are
undirected. Both choices are deliberate.

*Adjacent, not merely co-occurring*: the two differ. Across the corpus 802 pairs
are ever adjacent against 1,428 that merely share a cursus, and the ratio
separates them — `quaestor -- tribunus` is adjacent in 67 of 67 careers that
contain both, `flamen -- praefectus` in only 41 of 73. The first is a step
sequence, the second two posts that happen to appear in one life.

*Undirected*: Latin cursus inscriptions are written both ascending and
descending, and the corpus does not record which convention a given text uses.
Reading `order` as promotion direction would therefore invent a finding. Taking
adjacency alone keeps what the data supports — which posts sat next to each
other in a career — and discards what it does not.

What this buys is the question the undirected co-occurrence networks could not
reach: how sectors connect. position_type gives each step a sector, and the
adjacent transitions between sectors are where movement between military,
municipal and provincial service becomes visible.

Imperial titulature is excluded as in build_position_cooccurrence.py; without it
the top edges are `pontifex -- tribunicia potestas` and the rest of the imperial
styling, which is not a career.

Usage:
    venv/bin/python network_analysis/chen_method/build_cursus_network.py
    venv/bin/python network_analysis/chen_method/build_cursus_network.py --level type
    venv/bin/python network_analysis/chen_method/build_cursus_network.py --province Numidia
    venv/bin/python network_analysis/chen_method/build_cursus_network.py --all-pairs
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
sys.path.insert(0, str(HERE))

from build_deity_network import CORPUS, louvain  # noqa: E402
from build_position_cooccurrence import TITULATURE  # noqa: E402
from build_nomen_cooccurrence import is_imperial_person  # noqa: E402
from build_cooccurrence_network import null_modularity_onemode  # noqa: E402

# Equivalence groups for `--level abstract`. 316 distinct positions survive in
# the cursus data, which is far too many to read as a graph, and the tail is
# mostly spelling variants and ranks that differ by collegiate size rather than
# by function. Each group below was checked against the actual vocabulary; the
# merge takes the position count from 316 to 275 and, more to the point, lifts
# the top-20 coverage from 73% to 81%.
#
# What is deliberately NOT merged: flamen, pontifex, sacerdos and augur stay
# apart. They are the four substantive priesthoods and collapsing them would
# erase the local-priesthood structure that section 1-5 rests on. Likewise
# praefectus and tribunus keep their own nodes despite spanning military and
# civil use -- the corpus does not record which sense is meant, and guessing
# would be worse than leaving them.
ABSTRACT_GROUPS = {
    # Orthographic and formulaic variants of the municipal duovirate.
    'duovir': ['duumvir', 'iivir', 'duumviralicius', 'iiviralicius',
               'duovir quinquennalis'],
    'aedilis': ['aedilicius'],
    # Boards that differ only in how many members they had.
    'board-magistrate': ['triumvir', 'decemvir', 'quattuorvir', 'iiivir',
                         'iiiivir', 'xvir', 'sevir', 'septemvir',
                         'duodecimvir', 'quinquevir', 'octovir', 'iiiiiivir'],
    # Roman priestly colleges held as honours alongside a senatorial career,
    # as distinct from the municipal priesthoods above.
    'minor-priest': ['sodalis', 'fetialis', 'quindecimvir',
                     'septemvir epulonum', 'epulo', 'salius', 'lupercus'],
    # Status markers rather than posts: they say which order a man belonged to.
    'senatorial-rank': ['clarissimus', 'clarissimus vir', 'vir clarissimus',
                        'consularis', 'sexfascalis', 'patricius', 'allectus',
                        'adlectus'],
    # Rank and file, including the discharged.
    'soldier': ['miles', 'veteranus', 'eques', 'duplicarius', 'hastatus',
                'tesserarius', 'acceptarius'],
    # Below the centurionate plus the centurion himself: the career grade that
    # a soldier could reach without equestrian status.
    'nco': ['centurio', 'optio', 'signifer', 'beneficiarius', 'cornicularius',
            'frumentarius', 'custos', 'armorum', 'principalis', 'adiutor'],
}

_ABSTRACT = {v: k for k, vs in ABSTRACT_GROUPS.items() for v in vs}


def abstract(label: str) -> str:
    """Map a position onto its equivalence group, or return it unchanged."""
    return _ABSTRACT.get(label, label)


def iter_cursus(corpus: Path, province=None, include_imperial=False,
                level='position'):
    """Yield one ordered list of career steps per person.

    Steps with no `order` are dropped rather than appended: their position in
    the sequence is unknown, and guessing it would manufacture adjacencies.
    Consecutive duplicates are collapsed, since `aedilis, aedilis` is one post
    recorded twice, not a step.
    """
    for path in sorted(corpus.glob('*/*/*_career.json')):
        if province and path.parts[-3].lower() != province.lower().replace(' ', '_'):
            continue
        try:
            data = json.load(open(path, encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            continue
        for rec in data:
            for person in rec.get('persons', []):
                if not include_imperial and is_imperial_person(person):
                    continue
                steps = []
                for c in (person.get('career_path') or []):
                    order = c.get('order')
                    if order is None:
                        continue
                    if level == 'type':
                        lab = (c.get('position_type') or '').strip().lower()
                    else:
                        lab = (c.get('position_abstract')
                               or c.get('position_normalized') or '').strip().lower()
                    if not lab or lab in ('other', 'unknown'):
                        continue
                    if (not include_imperial and level == 'position'
                            and lab in TITULATURE):
                        continue
                    steps.append((order, lab))
                steps.sort(key=lambda s: s[0])
                seq = [lab for _, lab in steps]
                deduped = [lab for i, lab in enumerate(seq)
                           if i == 0 or lab != seq[i - 1]]
                if len(deduped) >= 2:
                    yield rec.get('edcs_id'), deduped


def adjacency_pairs(sequences, all_pairs=False):
    """Count each pair once per cursus.

    Once per career, not once per occurrence: a cursus alternating
    `duovir, flamen, duovir` evidences one kind of link, and counting it twice
    would weight verbose inscriptions rather than careers.
    """
    pairs = Counter()
    for seq in sequences:
        if all_pairs:
            found = {tuple(sorted((a, b)))
                     for a, b in combinations(sorted(set(seq)), 2) if a != b}
        else:
            found = {tuple(sorted((a, b))) for a, b in zip(seq, seq[1:]) if a != b}
        for key in found:
            pairs[key] += 1
    return pairs


def permutation(sequences, observed, trials, all_pairs=False, seed=42):
    """Expected adjacency when posts are reshuffled across careers.

    Each career keeps its length and each post its total number of
    attestations; only which post sits at which slot is randomised. A surviving
    deviation is therefore about which posts follow one another, not about how
    common a post is or how long a career the inscription records.
    """
    rng = random.Random(seed)
    lengths = [len(s) for s in sequences]
    pool = [lab for s in sequences for lab in s]

    null = defaultdict(list)
    for _ in range(trials):
        rng.shuffle(pool)
        cur = Counter()
        i = 0
        for n in lengths:
            if i + n > len(pool):
                i = 0
            chunk = pool[i:i + n]
            i += n
            if all_pairs:
                found = {tuple(sorted((a, b)))
                         for a, b in combinations(sorted(set(chunk)), 2) if a != b}
            else:
                found = {tuple(sorted((a, b)))
                         for a, b in zip(chunk, chunk[1:]) if a != b}
            for key in found:
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
    ap.add_argument('--level', choices=('position', 'abstract', 'type'),
                    default='position',
                    help='position_abstract (default); `abstract` additionally '
                         'merges spelling variants and equivalent ranks; '
                         '`type` gives the eight sectors')
    ap.add_argument('--all-pairs', action='store_true',
                    help='link every pair in a cursus, not only adjacent steps '
                         '(for comparison: adjacency is the informative one)')
    ap.add_argument('--include-imperial', action='store_true')
    ap.add_argument('--min-weight', type=int, default=2)
    ap.add_argument('--min-pair-obs', type=int, default=8)
    ap.add_argument('--province', default=None)
    ap.add_argument('--permutations', type=int, default=500)
    ap.add_argument('--null-trials', type=int, default=40)
    ap.add_argument('--out', default=str(HERE / 'output'))
    args = ap.parse_args()

    tag = {'position': 'cursus', 'abstract': 'cursus_abstract',
           'type': 'cursus_type'}[args.level]
    if args.all_pairs:
        tag += '_allpairs'
    if args.include_imperial:
        tag += '_with_imperial'
    if args.province:
        tag += '_' + re.sub(r'\W+', '_', args.province.lower())
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    entries = list(iter_cursus(CORPUS, args.province, args.include_imperial,
                               'position' if args.level == 'abstract'
                               else args.level))
    sequences = [seq for _eid, seq in entries]
    if args.level == 'abstract':
        sequences = [[abstract(lab) for lab in seq] for seq in sequences]
        # Merging can make neighbours identical (`duovir, duumvir`); collapse
        # them, exactly as iter_cursus does for raw repeats.
        sequences = [[lab for i, lab in enumerate(seq)
                      if i == 0 or lab != seq[i - 1]] for seq in sequences]
        sequences = [seq for seq in sequences if len(seq) >= 2]

    with open(outdir / f'report_{tag}.txt', 'w', encoding='utf-8') as fh:
        def emit(s=''):
            print(s)
            fh.write(s + '\n')

        emit(f'province: {args.province or "ALL"}')
        emit(f'label: {args.level}')
        emit(f'edges: {"every pair in a cursus" if args.all_pairs else "ADJACENT steps only"}')
        emit(f'emperors: {"included" if args.include_imperial else "excluded"}')
        emit(f'careers with 2+ ordered steps: {len(sequences)}')
        if not sequences:
            emit('no usable cursus')
            return 1
        emit('career length: ' + ', '.join(
            f'{k}:{v}' for k, v in sorted(Counter(len(s) for s in sequences).items())[:8]))

        pairs = adjacency_pairs(sequences, args.all_pairs)
        # Adjacency is a strict subset of co-occurrence; reporting both makes
        # the difference between "followed" and "merely shared a career" legible.
        cooc = adjacency_pairs(sequences, True)
        emit(f'distinct adjacent pairs: {len(adjacency_pairs(sequences, False))}'
             f'   distinct co-occurring pairs: {len(cooc)}')

        g = nx.Graph()
        for (a, b), w in sorted(pairs.items()):
            if w >= args.min_weight:
                g.add_edge(a, b, weight=w)
        if g.number_of_edges() == 0:
            emit('no pair survives --min-weight')
            return 1
        emit(f'\n=== cursus adjacency graph (min weight {args.min_weight}) ===')
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
        for c in sorted(comms, key=len, reverse=True)[:6]:
            emit(f'  community ({len(c)}): ' + ', '.join(sorted(c)[:14]))

        emit(f'\n=== pair permutation test (n={args.permutations}, '
             f'pairs with obs >= {args.min_pair_obs}) ===')
        rows = [r for r in permutation(sequences, dict(pairs), args.permutations,
                                       args.all_pairs)
                if r[1] >= args.min_pair_obs]
        emit(f'{"pair":<48}{"obs":>6}{"exp":>9}{"z":>9}{"adj/cooc":>10}')
        for z, obs, mean, (a, b) in rows:
            ratio = obs / cooc[(a, b)] if cooc.get((a, b)) else float('nan')
            emit(f'{a + " -- " + b:<48}{obs:>6}{mean:>9.1f}{z:>+9.2f}{ratio:>10.2f}')

        sig = [r for r in rows if r[0] >= 1.96]
        neg = [r for r in rows if r[0] <= -1.96]
        emit(f'\nsignificant at |z| >= 1.96: {len(sig)} positive, {len(neg)} negative '
             f'(of {len(rows)} tested)')
        emit('adj/cooc = of the careers holding both posts, the share where they '
             'were consecutive')

        nx.write_graphml(g, outdir / f'{tag}.graphml')
        with open(outdir / f'{tag}.json', 'w', encoding='utf-8') as jf:
            json.dump({
                'province': args.province,
                'level': args.level,
                'all_pairs': args.all_pairs,
                'include_imperial': args.include_imperial,
                'careers': len(sequences),
                'density': nx.density(g),
                'modularity': q,
                'null_mean': statistics.mean(nulls) if nulls else None,
                'pairs': [{'a': a, 'b': b, 'obs': obs, 'expected': mean, 'z': z,
                           'adj_share': (obs / cooc[(a, b)]
                                         if cooc.get((a, b)) else None)}
                          for z, obs, mean, (a, b) in rows],
            }, jf, ensure_ascii=False, indent=1)
        emit(f'\nwritten: {outdir}/report_{tag}.txt, {tag}.graphml, {tag}.json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
