#!/usr/bin/env python3
"""Generate benchmark instances for measuring clause deletion.

These are NOT regression tests - run_tests.py globs tests/uf20-91, tests/sat and
tests/unsat, and deliberately does not look here. They exist because the
regression corpus is far too easy to exercise clause deletion: a typical
uf20-91 instance finishes in 14 conflicts, and full12 - the hardest instance in
the repo - takes 2048, clearing Glucose's default 2000-conflict reduce
threshold by 48.

Generated rather than vendored so the baseline stays reproducible from a clean
checkout without adding megabytes of CNF to the repo.

  python3 tests/gen_bench.py [outdir]        # default: tests/bench
"""
import os
import random
import sys


def write_cnf(path, nvars, clauses, comment):
    with open(path, "w") as f:
        f.write("c %s\n" % comment)
        f.write("p cnf %d %d\n" % (nvars, len(clauses)))
        for c in clauses:
            f.write(" ".join(str(l) for l in c) + " 0\n")


def pigeonhole(pigeons, holes):
    """php(p, h): p pigeons into h holes. UNSAT whenever p > h, and
    exponentially hard for resolution - so learnt clauses pile up without
    bound, which is exactly the pressure clause deletion is meant to relieve."""
    def var(i, j):
        return i * holes + j + 1

    clauses = []
    for i in range(pigeons):                      # every pigeon gets a hole
        clauses.append([var(i, j) for j in range(holes)])
    for j in range(holes):                        # no hole takes two pigeons
        for a in range(pigeons):
            for b in range(a + 1, pigeons):
                clauses.append([-var(a, j), -var(b, j)])
    return pigeons * holes, clauses


def full(n):
    """Every sign combination over n variables: 2^n clauses, UNSAT by
    construction. Same family as the repo's full3/4/8/12."""
    clauses = []
    for mask in range(1 << n):
        clauses.append([(v + 1) if (mask >> v) & 1 else -(v + 1) for v in range(n)])
    return n, clauses


def rand3(n, ratio, seed):
    """Uniform random 3-SAT at the phase transition - the uf20-91 recipe, scaled
    up. Roughly half satisfiable at ratio 4.26."""
    rng = random.Random(seed)
    m = int(n * ratio)
    clauses = []
    for _ in range(m):
        vs = rng.sample(range(1, n + 1), 3)
        clauses.append([v if rng.random() < 0.5 else -v for v in vs])
    return n, clauses


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "bench")
    os.makedirs(outdir, exist_ok=True)

    made = []

    for p in (7, 8, 9, 10, 11):
        nv, cls = pigeonhole(p, p - 1)
        name = "php%d_%d.cnf" % (p, p - 1)
        write_cnf(os.path.join(outdir, name), nv, cls,
                  "pigeonhole %d pigeons %d holes, UNSAT" % (p, p - 1))
        made.append((name, nv, len(cls)))

    for n in (13, 14, 15, 16, 17):
        nv, cls = full(n)
        name = "full%d.cnf" % n
        write_cnf(os.path.join(outdir, name), nv, cls,
                  "all %d sign combinations over %d vars, UNSAT" % (1 << n, n))
        made.append((name, nv, len(cls)))

    for n in (100, 150, 200, 250):
        for seed in (1, 2, 3):
            nv, cls = rand3(n, 4.26, seed)
            name = "rand3_%d_s%d.cnf" % (n, seed)
            write_cnf(os.path.join(outdir, name), nv, cls,
                      "random 3-SAT n=%d ratio=4.26 seed=%d" % (n, seed))
            made.append((name, nv, len(cls)))

    print("wrote %d instances to %s" % (len(made), outdir))
    for name, nv, nc in made:
        print("  %-18s %5d vars %7d clauses" % (name, nv, nc))


if __name__ == "__main__":
    main()
