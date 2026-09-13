#!/usr/bin/env python3
"""Regression suite for the SAT solver.

Runs ./src/sat over every instance in tests/, checks the verdict against the
expected one, and independently verifies both kinds of answer:

  SAT   - re-reads the CNF from disk and checks the reported model against it
  UNSAT - re-runs with SAT_PROOF set and hands the DRAT proof to drat-trim

Neither check trusts the solver's own state. Proof checking is skipped with a
notice when drat-trim is not installed, so a fresh clone still runs the suite.
Exit status 0 = all passed.
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(os.path.join(__file__, "..")))
SAT = os.path.join(ROOT, "src", "sat")

SAT_EXIT, UNSAT_EXIT = 10, 20


def find_drat_trim():
    """$DRAT_TRIM, then PATH, then a checkout sitting beside the repo."""
    env = os.environ.get("DRAT_TRIM")
    if env:
        return env if os.access(env, os.X_OK) else None

    found = shutil.which("drat-trim")
    if found:
        return found

    sibling = os.path.join(os.path.dirname(ROOT), "drat-trim", "drat-trim")
    return sibling if os.access(sibling, os.X_OK) else None


def check_proof(path, drat_trim):
    """Re-solve with proof logging on and verify the proof independently."""
    fd, proof = tempfile.mkstemp(suffix=".drat")
    os.close(fd)
    try:
        env = dict(os.environ, SAT_PROOF=proof)
        r = subprocess.run([SAT, path], capture_output=True, text=True, env=env)
        if r.returncode != UNSAT_EXIT:
            return f"verdict changed to rc={r.returncode} when writing a proof"

        v = subprocess.run([drat_trim, path, proof], capture_output=True, text=True)
        # drat-trim draws progress with \r, so "s VERIFIED" is not line-anchored.
        out = (v.stdout + v.stderr).replace("\r", "\n")
        if "s VERIFIED" in out:
            return None

        reason = next((l for l in out.splitlines() if l.startswith("s ")), "")
        return "proof not verified" + (f": {reason}" if reason else "")
    finally:
        os.unlink(proof)


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


def check(path, expect, drat_trim=None):
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
    elif drat_trim:
        return check_proof(path, drat_trim)
    return None


def run_group(name, pattern, expect, drat_trim=None):
    files = sorted(glob.glob(os.path.join(ROOT, pattern)))
    if not files:
        print(f"  {name}: no instances found ({pattern})")
        return 0, 0
    bad = 0
    for f in files:
        err = check(f, expect, drat_trim)
        if err:
            bad += 1
            print(f"  FAIL {os.path.relpath(f, ROOT)}: {err}")
    print(f"  {name}: {len(files) - bad}/{len(files)} passed")
    return len(files), bad


def main():
    if not os.access(SAT, os.X_OK):
        print("solver not built - run:  cd src && make")
        return 1

    drat_trim = find_drat_trim()

    total = failed = 0
    print("Regression suite")
    if drat_trim:
        print(f"  proof checking via {drat_trim}")
    else:
        print("  proof checking SKIPPED - drat-trim not found "
              "(set DRAT_TRIM, or put it on PATH)")

    for name, pattern, expect in [
        ("satisfiable  (uf20-91)", "tests/uf20-91/*.cnf", SAT_EXIT),
        ("satisfiable  (edge)",    "tests/sat/*.cnf",     SAT_EXIT),
        ("unsatisfiable",          "tests/unsat/*.cnf",   UNSAT_EXIT),
    ]:
        n, bad = run_group(name, pattern, expect, drat_trim)
        total += n
        failed += bad

    print(f"\n{total - failed}/{total} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
