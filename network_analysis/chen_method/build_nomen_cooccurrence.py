#!/usr/bin/env python3
"""
Gentilicium x gentilicium co-occurrence between people in one inscription.

Third variant of the within-inscription question, after benefaction objects
(build_cooccurrence_network.py) and offices (build_position_cooccurrence.py).
The unit is again the edcs_id, and the tie is between two families named in the
same text.

Two filters decide whether this measures anything.

**Declared family ties are dropped.** A funerary monument naming a man, his
wife and his freedmen would otherwise produce the finding that relatives appear
together, which is a tautology. The corpus marks these: person_relationships
carries a type per person pair, and 3,404 of the 17,673 cross-gentilicium pairs
are `family`. Dropping them leaves patronage, colleague ties, and the 12,035
pairs with no declared relation — co-dedicators, officials named alongside each
other — which is where a non-obvious result could live. --keep-family restores
them for comparison.

**Gender forms are merged.** Sittius and Sittia are one family, and counting
them as two nodes puts `Sittius -- Sittia` at the top of the table as an
artefact of Latin morphology. Only the -ius/-ia alternation is collapsed, plus
doubled consonants (Aurellius -> Aurelius). A broader rule was tried and
rejected: stripping -us/-a as well merged Sabinus into Sabinia and Titus into
Titia, which are praenomina and cognomina, not the same family.

Note this differs from build_nomen_network.py and concentration.py, which keep
Sittius and Sittia apart (README section 1-0b reports them as separate rows).
That is right for a place-based network, where the two forms are independent
attestations; it is wrong here, where they sit in one text by construction.

Imperial gentilicia go too, reusing build_nomen_network.IMPERIAL_NOMINA: Iulius,
Aurelius and the rest follow the grant of citizenship rather than local kinship,
and they appear everywhere. Without the filter 4,539 inscriptions qualify and
the top pairs are deified emperors; with it, 1,917 remain.

Usage:
    venv/bin/python network_analysis/chen_method/build_nomen_cooccurrence.py
    venv/bin/python network_analysis/chen_method/build_nomen_cooccurrence.py --keep-family
    venv/bin/python network_analysis/chen_method/build_nomen_cooccurrence.py --no-merge-gender
    venv/bin/python network_analysis/chen_method/build_nomen_cooccurrence.py --province Numidia
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
from build_cooccurrence_network import null_modularity_onemode  # noqa: E402

# Relation types that make a tie uninformative. `family` is the whole point of
# the filter; the rest are kept because a dedication or a shared office is a
# claim about public life rather than about descent.
UNINFORMATIVE_RELATIONS = {'family'}

# Emperors are excluded as *people*; their gentilicia are not. The two are
# different claims. Iulius, Aurelius and Flavius were conferred with citizenship
# and so track when a community was enfranchised rather than local kinship --
# which is why build_nomen_network.py drops them from the place-based network.
# Co-occurrence asks a different question: whether two families are named in one
# text. An Aurelius enfranchised in 212 is still a family standing next to
# another family, so the gentilicium stays. What must go is the emperor himself,
# because every dedication names him and he would tie every text to every other.
#
# social_status carries the marker explicitly and is the reliable signal.
# build_deity_network.is_imperial is NOT used here: it matches on name tokens for
# the deity network, and on person records it also catches `Iulia Saturnina` and
# `Iulia Rogata` (ordinary provincial women), the bare praenomina `Marcus` and
# `Lucius`, and the god `Saturnus Augustus` -- 4,409 person-records whose status
# is not imperial at all.
IMPERIAL_STATUS = {'emperor', 'empress', 'imperial-family'}


def is_imperial_person(person) -> bool:
    """True for an emperor, empress or member of the imperial house.

    Matched exactly, not by substring: `augustalis` is a municipal priesthood
    and `imperial-slave` is a slave of the household, neither of them rulers.
    """
    return (person.get('social_status') or '').strip().lower() in IMPERIAL_STATUS


def canonical(nomen: str, merge_gender: bool = True) -> str:
    """Normalise one gentilicium, or return '' if it is unusable.

    Editorial brackets go first (build_nomen_network does the same, so
    `[Iul]ius` and `Iulius` are one family). Then doubled consonants, which are
    an orthographic variant rather than a different name.
    """
    n = re.sub(r'[\[\]()<>?]', '', nomen or '').strip().lower()
    if len(n) <= 2 or '-' in n:
        return ''
    n = re.sub(r'(.)\1', r'\1', n)
    if merge_gender:
        # Only -ius/-ia. Stripping a bare -us or -a as well would fold
        # cognomina and praenomina into families: Sabinus into Sabinia,
        # Titus into Titia, Verus into Verria.
        if n.endswith('ius'):
            return n[:-3] + 'i-'
        if n.endswith('ia'):
            return n[:-2] + 'i-'
    return n


def iter_inscription_nomina(corpus: Path, province=None, include_imperial=False,
                            merge_gender=True):
    """edcs_id -> (person_id -> nomen, {frozenset(pair): relation type}).

    Keyed by person so the caller can look up the declared relation for any
    pair, which the family filter needs. Records sharing an edcs_id are pooled,
    as in the sibling scripts; person_id is unique only within a record, so it
    is paired with the person's name to keep two people distinct.
    """
    nomina = defaultdict(dict)
    relations = defaultdict(dict)
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
            local = {}
            for person in rec.get('persons', []):
                name = person.get('person_name') or ''
                if not include_imperial and is_imperial_person(person):
                    continue
                nom = canonical(person.get('nomen'), merge_gender)
                if not nom:
                    continue
                pid = person.get('person_id')
                key = (pid, name)
                local[pid] = key
                nomina[eid][key] = nom
            for r in (rec.get('person_relationships') or []):
                a, b = r.get('source_person_id'), r.get('target_person_id')
                if a in local and b in local and a != b:
                    relations[eid][frozenset((local[a], local[b]))] = r.get('type')
    return nomina, relations


def person_key(name: str) -> str:
    """Letters only, so transcription variants of one person collapse.

    `Rut[i]/[l]ius Gallicu(s)` and `(R)utiliu(m) <G=C>allicu(m)` are the same
    man; the corpus records each inscription separately and does not resolve
    identity across them.
    """
    n = re.sub(r'\([^)]*\)|<[^>]*>|[\[\]/.]', '', (name or '').lower())
    return re.sub(r'[^a-z]', '', n)


def build_sets(nomina, dedupe_people=False):
    """edcs_id -> set of distinct gentilicia (for the node set and margins).

    With dedupe_people, inscriptions naming the same set of individuals count
    once. Boundary markers make this matter: `Rutilius Gallicus` and `Sentius
    Caecilianus` commissioned a series of termini, and each stone repeats both
    names, so the raw count reads 12 independent ties where there is one
    surveying commission. Corpus-wide only 4.1% of inscriptions share a
    signature, but they concentrate in the highest-z pairs.
    """
    sets = {}
    seen_signatures = {}
    for eid, by_person in nomina.items():
        labels = set(by_person.values())
        if len(labels) <= 1:
            continue
        if dedupe_people:
            sig = tuple(sorted(person_key(k[1]) for k in by_person))
            if sig in seen_signatures:
                continue
            seen_signatures[sig] = eid
        sets[eid] = labels
    return sets


def informative_pairs(nomina, relations, sets, keep_family=False):
    """Count a pair once per inscription, skipping declared-family ties.

    A pair is dropped only when *every* person-combination carrying it is
    marked family: two Caecilii and a Pompeius where one link is kinship and
    another is not still evidences the non-kin tie.
    """
    pairs = Counter()
    for eid in sets:
        by_person = nomina[eid]
        rel = relations.get(eid, {})
        seen = set()
        people = sorted(by_person.items(), key=lambda kv: (str(kv[0][1]), kv[1]))
        for (k_a, nom_a), (k_b, nom_b) in combinations(people, 2):
            if nom_a == nom_b:
                continue
            if not keep_family:
                if rel.get(frozenset((k_a, k_b))) in UNINFORMATIVE_RELATIONS:
                    continue
            seen.add(tuple(sorted((nom_a, nom_b))))
        for key in seen:
            pairs[key] += 1
    return pairs


def permutation(nomina, relations, sets, observed, trials, keep_family=False,
                seed=42):
    """Expected co-occurrence when gentilicia are reshuffled across people.

    The person structure is held fixed — same inscriptions, same number of
    people, same declared relations between those person slots — and only which
    family name sits on which person is randomised. The family filter is then
    applied identically to the observed and the simulated side, so the two are
    measured the same way.
    """
    rng = random.Random(seed)
    shape = []
    pool = []
    for eid in sorted(sets):
        people = sorted(nomina[eid].items(), key=lambda kv: (str(kv[0][1]), kv[1]))
        keys = [k for k, _ in people]
        shape.append((eid, keys))
        pool.extend(nom for _, nom in people)

    null = defaultdict(list)
    for _ in range(trials):
        rng.shuffle(pool)
        cur = Counter()
        i = 0
        for eid, keys in shape:
            assigned = {}
            for k in keys:
                if i >= len(pool):
                    i = 0
                assigned[k] = pool[i]
                i += 1
            rel = relations.get(eid, {})
            seen = set()
            for k_a, k_b in combinations(keys, 2):
                a, b = assigned[k_a], assigned[k_b]
                if a == b:
                    continue
                if not keep_family:
                    if rel.get(frozenset((k_a, k_b))) in UNINFORMATIVE_RELATIONS:
                        continue
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
    ap.add_argument('--keep-family', action='store_true',
                    help='keep pairs declared `family` (default: drop — '
                         'relatives sharing a tombstone is a tautology)')
    ap.add_argument('--no-merge-gender', dest='merge_gender', action='store_false',
                    help='keep Sittius and Sittia as separate nodes')
    ap.add_argument('--include-imperial', action='store_true',
                    help='keep emperors as people (default: drop them; their '
                         'gentilicia are kept either way)')
    ap.add_argument('--dedupe-people', action='store_true',
                    help='count inscriptions naming the same individuals once '
                         '(boundary-marker series inflate the raw counts)')
    ap.add_argument('--min-weight', type=int, default=2)
    ap.add_argument('--min-pair-obs', type=int, default=5)
    ap.add_argument('--province', default=None)
    ap.add_argument('--permutations', type=int, default=500)
    ap.add_argument('--null-trials', type=int, default=40)
    ap.add_argument('--out', default=str(HERE / 'output'))
    args = ap.parse_args()

    tag = 'nomen_cooc'
    if args.keep_family:
        tag += '_withfamily'
    if not args.merge_gender:
        tag += '_nomerge'
    if args.include_imperial:
        tag += '_with_imperial'
    if args.dedupe_people:
        tag += '_dedup'
    if args.province:
        tag += '_' + re.sub(r'\W+', '_', args.province.lower())
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    nomina, relations = iter_inscription_nomina(
        CORPUS, args.province, args.include_imperial, args.merge_gender)
    sets = build_sets(nomina, args.dedupe_people)

    with open(outdir / f'report_{tag}.txt', 'w', encoding='utf-8') as fh:
        def emit(s=''):
            print(s)
            fh.write(s + '\n')

        emit(f'province: {args.province or "ALL"}')
        emit(f'gender forms: {"merged (-ius/-ia)" if args.merge_gender else "SEPARATE"}')
        emit(f'declared family ties: {"KEPT" if args.keep_family else "dropped"}')
        emit(f'emperors as people: '
             f'{"INCLUDED" if args.include_imperial else "excluded"}'
             '  (imperial gentilicia such as Iulius are KEPT)')
        emit(f'repeated individuals: '
             f'{"deduplicated" if args.dedupe_people else "kept (see --dedupe-people)"}')
        emit(f'inscriptions with >=2 distinct gentilicia: {len(sets)}')

        if len(sets) < 2:
            emit('too few inscriptions to build a network')
            return 1

        size_dist = Counter(len(v) for v in sets.values())
        emit('gentilicia per inscription: '
             + ', '.join(f'{k}:{v}' for k, v in sorted(size_dist.items())[:8]))

        pairs = informative_pairs(nomina, relations, sets, args.keep_family)
        n_dropped = sum(len(r) for r in relations.values())
        emit(f'person-pairs carrying a declared relation: {n_dropped}')

        g = nx.Graph()
        # Sorted insertion keeps the null distribution reproducible; networkx
        # preserves edge order and double_edge_swap walks it.
        for (a, b), w in sorted(pairs.items()):
            if w >= args.min_weight:
                g.add_edge(a, b, weight=w)
        if g.number_of_edges() == 0:
            emit('no pair survives --min-weight')
            return 1
        emit(f'\n=== co-occurrence graph (min weight {args.min_weight}) ===')
        emit(f'nodes {g.number_of_nodes()}  edges {g.number_of_edges()}  '
             f'density {nx.density(g):.4f}')

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
        rows = [r for r in permutation(nomina, relations, sets, dict(pairs),
                                       args.permutations, args.keep_family)
                if r[1] >= args.min_pair_obs]
        if not rows:
            emit(f'no pair reaches obs >= {args.min_pair_obs}; '
                 'the corpus is too thin at this threshold')
        else:
            emit(f'{"pair":<44}{"obs":>6}{"exp":>9}{"z":>9}')
            for z, obs, mean, (a, b) in rows:
                emit(f'{a + " -- " + b:<44}{obs:>6}{mean:>9.1f}{z:>+9.2f}')
        sig = [r for r in rows if r[0] >= 1.96]
        neg = [r for r in rows if r[0] <= -1.96]
        emit(f'\nsignificant at |z| >= 1.96: {len(sig)} positive, {len(neg)} negative '
             f'(of {len(rows)} tested)')

        nx.write_graphml(g, outdir / f'{tag}.graphml')
        with open(outdir / f'{tag}.json', 'w', encoding='utf-8') as jf:
            json.dump({
                'province': args.province,
                'merge_gender': args.merge_gender,
                'keep_family': args.keep_family,
                'include_imperial': args.include_imperial,
                'inscriptions_multi': len(sets),
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
