#!/usr/bin/env python3
"""Write satisfiability-preserving shuffled copies of a DIMACS CNF.

A deterministic solver gives one sample per instance: a 40% difference between
two configurations on a single file may be nothing more than which path the
heuristics happened to take. Running both configurations over several shuffled
copies of the same formula measures that luck, so a real effect can be told
apart from it.

Each copy applies, under its own seed:
  - a random permutation of the variable names
  - a random sign flip per variable            (skipped with --no-flip)
  - a random literal order inside every clause (both solvers watch the first
    two literals initially, so this is part of the luck too)
  - a random clause order

None of these changes satisfiability, so every copy must get the same verdict
as the original - a cheap check that the shuffler itself is not broken.

Sign flips are the strongest perturbation: both solvers start with every phase
false, so flipping a variable moves the initial assignment. --no-flip keeps the
milder renaming-and-reordering-only version, for separating the two effects.

  python3 tests/shuffle_cnf.py IN.cnf [--seeds 1-10] [--no-flip] [--outdir DIR]

Copies are written as DIR/<name>.s<seed>.cnf (with --no-flip: .n<seed>.cnf).
DIR defaults to tests/shuffled/. The original is not rewritten; treat it as
seed 0.
"""
import argparse
import os
import random
import sys

ROOT = os.path.dirname(os.path.abspath(os.path.join(__file__, "..")))


def read_cnf(path):
    nvars, clauses, cur = None, [], []
    with open(path) as f:
        for line in f:
            tok = line.split()
            if not tok or tok[0] == "c":
                continue
            if tok[0] == "%":                       # SATLIB end marker
                break
            if tok[0] == "p":
                nvars = int(tok[2])
                continue
            for t in tok:
                v = int(t)
                if v == 0:
                    if cur:
                        clauses.append(cur)
                    cur = []
                else:
                    cur.append(v)
    if cur:
        clauses.append(cur)
    if nvars is None:
        sys.exit("error: no p line in %s" % path)
    return nvars, clauses


def shuffle(nvars, clauses, seed, flip):
    rng = random.Random(seed)

    perm = list(range(1, nvars + 1))
    rng.shuffle(perm)
    rename = [0] + perm                             # rename[v] = new name of v
    sign = [1] + [rng.choice((1, -1)) if flip else 1 for _ in range(nvars)]

    out = []
    for c in clauses:
        nc = [(1 if l > 0 else -1) * sign[abs(l)] * rename[abs(l)] for l in c]
        rng.shuffle(nc)
        out.append(nc)
    rng.shuffle(out)
    return out


def parse_seeds(s):
    seeds = []
    for part in s.split(","):
        if "-" in part:
            a, b = part.split("-")
            seeds.extend(range(int(a), int(b) + 1))
        else:
            seeds.append(int(part))
    return seeds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cnf")
    ap.add_argument("--seeds", default="1-5", help="e.g. 1-10 or 1,4,7 (default 1-5)")
    ap.add_argument("--no-flip", action="store_true", help="rename and reorder only")
    ap.add_argument("--outdir", default=os.path.join(ROOT, "tests", "shuffled"))
    args = ap.parse_args()

    nvars, clauses = read_cnf(args.cnf)
    name = os.path.splitext(os.path.basename(args.cnf))[0]
    tag = "n" if args.no_flip else "s"
    os.makedirs(args.outdir, exist_ok=True)

    for seed in parse_seeds(args.seeds):
        shuffled = shuffle(nvars, clauses, seed, not args.no_flip)
        path = os.path.join(args.outdir, "%s.%s%d.cnf" % (name, tag, seed))
        with open(path, "w") as f:
            f.write("c shuffled copy of %s, seed %d, flip=%s\n"
                    % (os.path.basename(args.cnf), seed, not args.no_flip))
            f.write("p cnf %d %d\n" % (nvars, len(shuffled)))
            for c in shuffled:
                f.write(" ".join(map(str, c)) + " 0\n")
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
