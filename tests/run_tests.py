#!/usr/bin/env python3
"""Regression suite for the SAT solver.

Runs ./src/sat over every instance in tests/, checks the verdict against the
expected one, and independently re-verifies every reported SAT model against
the CNF on disk. Exit status 0 = all passed.
"""
import glob
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(os.path.join(__file__, "..")))
SAT = os.path.join(ROOT, "src", "sat")

SAT_EXIT, UNSAT_EXIT = 10, 20


def read_clauses(path):
    clauses, cur = [], []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line[0] in "cp":
                continue
            if line[0] == "%":
                break
            for tok in line.split():
                try:
                    v = int(tok)
                except ValueError:
                    continue
                if v == 0:
                    if cur:
                        clauses.append(cur)
                        cur = []
                else:
                    cur.append(v)
    if cur:
        clauses.append(cur)
    return clauses


def parse_model(stdout):
    model = {}
    for line in stdout.splitlines():
        if line.startswith("v"):
            for tok in line.split()[1:]:
                v = int(tok)
                if v == 0:
                    break
                model[abs(v)] = v > 0
    return model


def check(path, expect):
    r = subprocess.run([SAT, path], capture_output=True, text=True)
    if r.returncode != expect:
        got = {SAT_EXIT: "SAT", UNSAT_EXIT: "UNSAT"}.get(r.returncode, f"rc={r.returncode}")
        want = "SAT" if expect == SAT_EXIT else "UNSAT"
        return f"expected {want}, got {got}"
    if expect == SAT_EXIT:
        model = parse_model(r.stdout)
        for c in read_clauses(path):
            if not any(model.get(abs(l), False) == (l > 0) for l in c):
                return f"model does not satisfy clause {c}"
    return None


def run_group(name, pattern, expect):
    files = sorted(glob.glob(os.path.join(ROOT, pattern)))
    if not files:
        print(f"  {name}: no instances found ({pattern})")
        return 0, 0
    bad = 0
    for f in files:
        err = check(f, expect)
        if err:
            bad += 1
            print(f"  FAIL {os.path.relpath(f, ROOT)}: {err}")
    print(f"  {name}: {len(files) - bad}/{len(files)} passed")
    return len(files), bad


def main():
    if not os.access(SAT, os.X_OK):
        print("solver not built - run:  cd src && make")
        return 1

    total = failed = 0
    print("Regression suite")
    for name, pattern, expect in [
        ("satisfiable  (uf20-91)", "tests/uf20-91/*.cnf", SAT_EXIT),
        ("satisfiable  (edge)",    "tests/sat/*.cnf",     SAT_EXIT),
        ("unsatisfiable",          "tests/unsat/*.cnf",   UNSAT_EXIT),
    ]:
        n, bad = run_group(name, pattern, expect)
        total += n
        failed += bad

    print(f"\n{total - failed}/{total} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
