#!/usr/bin/env python3
"""Which growth is the solver's fault? Pigeonhole against fullN.

  php(n+1, n)  Haken (1985): every resolution refutation is exponential in n,
               while the formula has only O(n^3) clauses. Measured: conflicts
               per size, taken as the median over shuffled copies because one
               file is one lucky or unlucky draw (see luck_test.py).
  fullN        all 2^n sign combinations over n variables. Minimally UNSAT -
               drop any clause and it becomes SAT - so every refutation uses
               every clause, at least 2^n - 1 resolution steps. Checked: is the
               solver's effort exactly 2^(n-1) conflicts and 2^(n-1) - 1
               decisions, i.e. linear in the size of the input?

Shuffled copies go to a temporary directory and are deleted afterwards; the
seeds make them reproducible.

  python3 tests/proof_complexity.py
  python3 tests/proof_complexity.py --seeds 1-10 --no-flip
"""
import argparse
import math
import os
import shutil
import statistics
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import shuffle_cnf  # noqa: E402

SAT = os.path.join(os.path.dirname(HERE), "src", "sat")
BENCH = os.path.join(HERE, "bench")
PHP = [("php7_6", 7), ("php8_7", 8), ("php9_8", 9), ("php10_9", 10), ("php11_10", 11)]
FULL = [("full13", 13), ("full14", 14), ("full15", 15), ("full16", 16), ("full17", 17)]


def solve(path):
    p = subprocess.run([SAT, path], capture_output=True, text=True)
    d = {}
    for line in p.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0] == "c":
            try:
                d[parts[1]] = int(parts[2])
            except ValueError:
                pass
    d["rc"] = p.returncode
    return d


def slope(xs, ys):
    """Least-squares slope of ys on xs."""
    mx, my = statistics.mean(xs), statistics.mean(ys)
    return (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) /
            sum((x - mx) ** 2 for x in xs))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seeds", default="1-5", help="shuffled copies per php size (default 1-5)")
    ap.add_argument("--no-flip", action="store_true", help="shuffle without sign flips")
    args = ap.parse_args()
    if not os.access(SAT, os.X_OK):
        sys.exit("solver not built - run:  cd src && make release")
    seeds = shuffle_cnf.parse_seeds(args.seeds)
    tmp = tempfile.mkdtemp(prefix="proof_complexity_")
    ok = True
    try:
        print("pigeonhole: n+1 pigeons, n holes   (shuffled: %d seeds, flip=%s)\n" % (
              len(seeds), not args.no_flip))
        print("%-9s %7s %7s %11s %13s %21s %8s" % (
              "instance", "vars", "clauses", "original", "median copies", "[min .. max]", "growth"))
        ns, logs, prev = [], [], None
        for name, pigeons in PHP:
            cnf = os.path.join(BENCH, name + ".cnf")
            orig = solve(cnf)
            nvars, clauses = shuffle_cnf.read_cnf(cnf)
            confl = []
            for s in seeds:
                path = os.path.join(tmp, "%s.%d.cnf" % (name, s))
                sh = shuffle_cnf.shuffle(nvars, clauses, s, not args.no_flip)
                with open(path, "w") as f:
                    f.write("p cnf %d %d\n" % (nvars, len(sh)))
                    for c in sh:
                        f.write(" ".join(map(str, c)) + " 0\n")
                r = solve(path)
                if r["rc"] != 20:
                    print("  %s seed %d: expected UNSAT, got rc %d" % (name, s, r["rc"]))
                    ok = False
                confl.append(r["conflicts"])
                os.remove(path)
            med = statistics.median(confl)
            growth = "%.2fx" % (med / prev) if prev else ""
            print("%-9s %7d %7d %11d %13.0f %10d .. %-8d %8s" % (
                  name, orig["vars"], orig["clauses"], orig["conflicts"], med,
                  min(confl), max(confl), growth))
            ns.append(pigeons)
            logs.append(math.log2(med))
            prev = med
        b = slope(ns, logs)
        print("\n  fit log2(median conflicts) ~ n: slope %.2f, i.e. about %.2fx more conflicts"
              " per added pigeon" % (b, 2 ** b))
        cl = [solve(os.path.join(BENCH, n + ".cnf"))["clauses"] for n, _ in PHP]
        bc = slope([math.log2(p) for _, p in PHP], [math.log2(c) for c in cl])
        print("  input size: clauses grow like n^%.1f - polynomial, while conflicts grow "
              "exponentially" % bc)

        print("\nfullN: all 2^n clauses of width n\n")
        print("%-8s %9s %10s %12s %10s %12s %16s" % (
              "instance", "clauses", "conflicts", "= 2^(n-1)?", "decisions", "= 2^(n-1)-1?",
              "conflicts/clause"))
        for name, n in FULL:
            r = solve(os.path.join(BENCH, name + ".cnf"))
            c_ok = r["conflicts"] == 2 ** (n - 1)
            d_ok = r["decisions"] == 2 ** (n - 1) - 1
            ok = ok and c_ok and d_ok and r["rc"] == 20
            print("%-8s %9d %10d %12s %10d %12s %16.3f" % (
                  name, r["clauses"], r["conflicts"], "yes" if c_ok else "NO",
                  r["decisions"], "yes" if d_ok else "NO", r["conflicts"] / r["clauses"]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
