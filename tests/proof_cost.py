#!/usr/bin/env python3
"""What does it cost to trust an UNSAT answer?

For each unsatisfiable benchmark instance:
  1. solve without a proof                          -> cycles
  2. solve with SAT_PROOF set                       -> cycles, proof size, lines
  3. check that proof with drat-trim                -> wall time, VERIFIED?
  4. optionally (--lrat) also have drat-trim emit LRAT, the format a formally
     verified checker such as cake_lpr consumes     -> LRAT size

Run 2 must follow exactly the same search as run 1 - proof logging is output
only - so every solver counter is compared between the two, and a mismatch is
flagged. Proofs are written to a temporary directory and deleted after each
instance.

  python3 tests/proof_cost.py                      # default UNSAT instances
  python3 tests/proof_cost.py --lrat
  python3 tests/proof_cost.py --instances php11_10,full17 --out FILE.csv

drat-trim is found like run_tests.py does: $DRAT_TRIM, PATH, ../drat-trim.
"""
import argparse
import csv
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cost_model as cm  # noqa: E402
from run_tests import find_drat_trim  # noqa: E402

INSTANCES = ["php9_8", "php10_9", "php11_10", "full15", "full16", "full17",
             "rand3_200_s1", "rand3_250_s2", "rand3_250_s3"]
FIELDS = ["inst", "conflicts", "base_cycles", "proof_cycles", "overhead_pct",
          "proof_bytes", "proof_adds", "proof_dels", "check_sec", "verified",
          "lrat_bytes", "lrat_sec", "same_search"]


def best_of(path, env, repeat, cutoff):
    best = cm.run_once(path, env)
    if best["wall"] < cutoff:
        for _ in range(repeat - 1):
            r = cm.run_once(path, env)
            if r["cycles"] and r["cycles"] < best["cycles"]:
                best = r
    return best


def count_lines(proof):
    adds = dels = 0
    with open(proof, "rb") as f:
        for line in f:
            if line.startswith(b"d "):
                dels += 1
            elif line.strip():
                adds += 1
    return adds, dels


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--instances", default=",".join(INSTANCES))
    ap.add_argument("--repeat", type=int, default=3, help="runs per solve, min cycles kept")
    ap.add_argument("--repeat-cutoff", type=float, default=5.0)
    ap.add_argument("--lrat", action="store_true", help="also time drat-trim emitting LRAT")
    ap.add_argument("--out", help="CSV path (default tests/proof_cost.csv)")
    args = ap.parse_args()

    if not os.access(cm.SAT, os.X_OK):
        sys.exit("solver not built - run:  cd src && make release")
    drat = find_drat_trim()
    if not drat:
        sys.exit("drat-trim not found (set DRAT_TRIM, or put it on PATH)")

    out = args.out or os.path.join(HERE, "proof_cost.csv")
    tmp = tempfile.mkdtemp(prefix="proof_cost_")
    rows = []
    try:
        with open(out, "w", newline="") as fh:
            for line in cm.header_lines(args):
                fh.write(line + "\n")
            fh.write("# drat-trim: %s\n" % drat)
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            w.writeheader()

            print("%-13s %9s %8s %9s %10s %10s %8s %9s %s" % (
                  "instance", "conflicts", "overhead", "proof MB", "additions",
                  "deletions", "check s", "verified", "" if not args.lrat else "LRAT MB / s"))
            for inst in args.instances.split(","):
                cnf = os.path.join(cm.BENCH, inst + ".cnf")
                proof = os.path.join(tmp, inst + ".drat")

                base = best_of(cnf, {}, args.repeat, args.repeat_cutoff)
                if base["verdict"] != "UNSAT":
                    print("%-13s skipped: %s, not UNSAT" % (inst, base["verdict"]))
                    continue
                prf = best_of(cnf, {"SAT_PROOF": proof}, args.repeat, args.repeat_cutoff)
                same = all(base.get(k) == prf.get(k) for k in cm.COUNTERS)

                adds, dels = count_lines(proof)
                t0 = time.perf_counter()
                chk = subprocess.run([drat, cnf, proof], capture_output=True, text=True)
                check_sec = time.perf_counter() - t0
                # drat-trim draws progress with \r, so the verdict is not at a
                # line start: match the substring, as run_tests.py does.
                verified = "s VERIFIED" in chk.stdout

                lrat_bytes = lrat_sec = ""
                if args.lrat:
                    lrat = os.path.join(tmp, inst + ".lrat")
                    t0 = time.perf_counter()
                    subprocess.run([drat, cnf, proof, "-L", lrat], capture_output=True, text=True)
                    lrat_sec = time.perf_counter() - t0
                    lrat_bytes = os.path.getsize(lrat) if os.path.exists(lrat) else 0
                    if os.path.exists(lrat):
                        os.remove(lrat)

                row = dict(inst=inst, conflicts=base["conflicts"],
                           base_cycles=base["cycles"], proof_cycles=prf["cycles"],
                           overhead_pct=100.0 * (prf["cycles"] / base["cycles"] - 1),
                           proof_bytes=os.path.getsize(proof), proof_adds=adds,
                           proof_dels=dels, check_sec=check_sec, verified=verified,
                           lrat_bytes=lrat_bytes, lrat_sec=lrat_sec, same_search=same)
                os.remove(proof)
                w.writerow(row)
                fh.flush()
                rows.append(row)

                ghz = base["cycles"] / base["wall"] / 1e9 if base["wall"] else 0
                print("%-13s %9d %+7.1f%% %9.1f %10d %10d %8.2f %9s %s%s" % (
                      inst, row["conflicts"], row["overhead_pct"], row["proof_bytes"] / 2**20,
                      adds, dels, check_sec, "yes" if verified else "NO",
                      "%.1f / %.2f" % (lrat_bytes / 2**20, lrat_sec) if args.lrat else "",
                      "" if same else "   <-- SEARCH CHANGED WITH PROOF LOGGING"), flush=True)
                print("%-13s solve %.2f s (%.0f cycles at %.2f GHz), checking / solving = %.2f" % (
                      "", base["wall"], base["cycles"], ghz,
                      check_sec / base["wall"] if base["wall"] else 0))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\nwrote %s" % out)
    return 0 if all(r["verified"] and r["same_search"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
