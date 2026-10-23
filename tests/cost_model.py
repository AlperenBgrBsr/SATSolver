#!/usr/bin/env python3
"""Per-operation cost model: can a few counts predict the solver's cycles?

Fits, by least squares over many runs,

    cycles  ~  a*skip + b*search + c*scan + d*conflicts  [+ e*decisions*vars]

  skip      visits that found lits[0] already true     (c visit_skip)
  search    visits that ran the replacement search     (moved + unit + conflict)
  scan      literals checked by those searches          (c scan_lits)
  conflicts per-conflict work: analyze, learn, backjump (c conflicts)
  decisions*vars   the O(n) pick_branch_lit scan - optional, --with-scan-term

so the coefficients come out in cycles per operation. Runs differ in mix
because each instance is solved under several clause-deletion schedules: a
bigger database means more skips per search, which is what lets the fit tell
the predictors apart.

Cycles and instructions come from /usr/bin/time -l (Apple Silicon reports
both), not from wall time. The fit minimises RELATIVE error - each run is
divided by its own cycle count - so the 20-second runs do not drown out the
0.2-second ones.

  python3 tests/cost_model.py collect                 # run everything, write CSV, fit
  python3 tests/cost_model.py fit FILE.csv            # refit, no solving
  python3 tests/cost_model.py fit FILE.csv --train php,full   # fit on these
                                                      # families, predict the rest
  python3 tests/cost_model.py fit FILE.csv --with-scan-term

Build first:  cd src && make release   (the counters must be in the binary).
"""
import argparse
import csv
import math
import os
import re
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SAT = os.path.join(ROOT, "src", "sat")
BENCH = os.path.join(HERE, "bench")

INSTANCES = ["php9_8", "php10_9", "php11_10",
             "full15", "full16", "full17",
             "rand3_200_s1", "rand3_200_s2", "rand3_200_s3",
             "rand3_250_s1", "rand3_250_s2", "rand3_250_s3"]
# (SAT_REDUCE_FIRST, SAT_REDUCE_INC). The last one switches deletion off.
SCHEDULES = [(100, 20), (2000, 300), (20000, 3000), (1000000000, 0)]

COUNTERS = ["vars", "conflicts", "decisions", "propagations", "clause_visits",
            "visit_skip", "visit_moved", "visit_unit", "visit_conflict",
            "scan_lits", "learnts", "max_learnts", "learnt_lits"]
FIELDS = (["inst", "family", "reduce_first", "reduce_inc", "verdict",
           "cycles", "instructions", "wall", "rss_kb"] + COUNTERS)


def family(inst):
    return re.match(r"[a-z]+", inst).group(0).rstrip("_")


# --- collection --------------------------------------------------------------

def run_once(path, env):
    e = dict(os.environ)
    e.update(env)
    t0 = time.perf_counter()
    p = subprocess.run(["/usr/bin/time", "-l", SAT, path], env=e,
                       capture_output=True, text=True)
    wall = time.perf_counter() - t0

    def grab(pattern):
        m = re.search(pattern, p.stderr)
        return int(m.group(1)) if m else 0

    row = {"verdict": {10: "SAT", 20: "UNSAT"}.get(p.returncode, "rc=%d" % p.returncode),
           "cycles": grab(r"(\d+)\s+cycles elapsed"),
           "instructions": grab(r"(\d+)\s+instructions retired"),
           "rss_kb": grab(r"(\d+)\s+maximum resident set size") // 1024,
           "wall": wall}
    for line in p.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0] == "c" and parts[1] in COUNTERS:
            row[parts[1]] = int(parts[2])
    return row


def header_lines(args):
    def cmd(c):
        try:
            return subprocess.run(c, capture_output=True, text=True, cwd=ROOT).stdout.strip()
        except OSError:
            return "?"
    try:
        build = open(os.path.join(ROOT, "src", ".build-mode")).read().strip()
    except OSError:
        build = "?"
    return [
        "# cost_model.py " + " ".join(sys.argv[1:]),
        "# generated %s" % time.strftime("%Y-%m-%d %H:%M:%S"),
        "# git %s%s" % (cmd(["git", "rev-parse", "--short", "HEAD"]),
                        " (dirty)" if cmd(["git", "status", "--porcelain", "--untracked-files=no"]) else ""),
        "# sat build: %s" % build,
        "# cpu: %s" % cmd(["sysctl", "-n", "machdep.cpu.brand_string"]),
        "# P-core L1d/L2: %s / %s bytes" % (cmd(["sysctl", "-n", "hw.perflevel0.l1dcachesize"]),
                                            cmd(["sysctl", "-n", "hw.perflevel0.l2cachesize"])),
        "# repeats: %d (min cycles kept; runs over %.0f s once)" % (args.repeat, args.repeat_cutoff),
    ]


def collect(args):
    if not os.access(SAT, os.X_OK):
        sys.exit("solver not built - run:  cd src && make release")
    probe = subprocess.run([SAT, os.path.join(HERE, "sat", sorted(os.listdir(os.path.join(HERE, "sat")))[0])],
                           capture_output=True, text=True).stdout
    if "visit_skip" not in probe:
        sys.exit("./src/sat does not print visit_skip - rebuild it with the visit counters")
    build = open(os.path.join(ROOT, "src", ".build-mode")).read()
    if "-O2" not in build or "-DNDEBUG" not in build:
        print("WARNING: src/sat is not a release build (%s) - timings will be off" % build.strip())

    out = args.out or os.path.join(HERE, "cost_model.csv")
    rows = []
    with open(out, "w", newline="") as fh:
        for line in header_lines(args):
            fh.write(line + "\n")
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for inst in args.instances.split(","):
            path = os.path.join(BENCH, inst + ".cnf")
            if not os.path.exists(path):
                print("skip %s: not found (make bench-gen)" % inst)
                continue
            for first, inc in SCHEDULES:
                env = {"SAT_REDUCE_FIRST": str(first), "SAT_REDUCE_INC": str(inc)}
                best = run_once(path, env)
                if best["wall"] < args.repeat_cutoff:
                    for _ in range(args.repeat - 1):
                        r = run_once(path, env)
                        # Counters are deterministic; only cycles vary.
                        if r["cycles"] and r["cycles"] < best["cycles"]:
                            best = r
                row = {"inst": inst, "family": family(inst), "reduce_first": first,
                       "reduce_inc": inc, **best}
                w.writerow({k: row.get(k, "") for k in FIELDS})
                fh.flush()
                rows.append(row)

                search = row["visit_moved"] + row["visit_unit"] + row["visit_conflict"]
                ok = (row["visit_skip"] + search == row["clause_visits"]
                      and row["visit_conflict"] == row["conflicts"])
                print("%-13s %-10d %-5s %6.2fs %14d cyc  IPC %.2f  rss %6d KB%s" % (
                      inst, first, row["verdict"], row["wall"], row["cycles"],
                      row["instructions"] / max(row["cycles"], 1), row["rss_kb"],
                      "" if ok else "   <-- COUNTER INVARIANT BROKEN"), flush=True)
    print("\nwrote %s" % out)
    return rows


# --- fitting -----------------------------------------------------------------

def predictors(r, with_scan_term):
    search = r["visit_moved"] + r["visit_unit"] + r["visit_conflict"]
    x = [("skip", r["visit_skip"]), ("search", search),
         ("scan", r["scan_lits"]), ("conflict", r["conflicts"])]
    if with_scan_term:
        x.append(("decision*var", r["decisions"] * r["vars"]))
    return x


def lstsq(A, y):
    """Least squares via normal equations, columns scaled first so counts in
    the 1e9 range and in the 1e4 range do not wreck the elimination."""
    n = len(A[0])
    scale = [max(abs(row[j]) for row in A) or 1.0 for j in range(n)]
    As = [[row[j] / scale[j] for j in range(n)] for row in A]
    M = [[sum(r[i] * r[j] for r in As) for j in range(n)] +
         [sum(r[i] * t for r, t in zip(As, y))] for i in range(n)]
    for c in range(n):
        p = max(range(c, n), key=lambda k: abs(M[k][c]))
        M[c], M[p] = M[p], M[c]
        if abs(M[c][c]) < 1e-12:
            raise ValueError("predictors are linearly dependent - drop one")
        for k in range(n):
            if k != c:
                f = M[k][c] / M[c][c]
                M[k] = [a - f * b for a, b in zip(M[k], M[c])]
    return [M[i][n] / M[i][i] / scale[i] for i in range(n)]


def fit_rows(rows, with_scan_term):
    # Relative error: divide every row by its own cycle count.
    A = [[v / r["cycles"] for _, v in predictors(r, with_scan_term)] for r in rows]
    return lstsq(A, [1.0] * len(rows))


def predict(r, coef, with_scan_term):
    return sum(c * v for c, (_, v) in zip(coef, predictors(r, with_scan_term)))


def fit(rows, args):
    for r in rows:
        for k in ["cycles", "instructions", "rss_kb", "reduce_first"] + COUNTERS:
            r[k] = int(r[k])
        r["wall"] = float(r["wall"])
    usable = [r for r in rows if r["cycles"] >= args.min_cycles]
    print("%d runs, %d used (%d under %.0e cycles dropped: startup dominates them)" % (
          len(rows), len(usable), len(rows) - len(usable), args.min_cycles))

    train = usable
    if args.train:
        fams = set(args.train.split(","))
        train = [r for r in usable if r["family"] in fams]
        print("training on families %s: %d runs; the rest are predicted out of sample"
              % (",".join(sorted(fams)), len(train)))

    npred = 5 if args.with_scan_term else 4
    if len(train) < 2 * npred:
        sys.exit("only %d training runs for %d coefficients - too few to fit "
                 "(lower --min-cycles, or collect more instances)" % (len(train), npred))
    coef = fit_rows(train, args.with_scan_term)
    names = [n for n, _ in predictors(train[0], args.with_scan_term)]

    # Stability: refit with each instance left out entirely.
    insts = sorted({r["inst"] for r in train})
    loo = []
    for inst in insts:
        sub = [r for r in train if r["inst"] != inst]
        try:
            loo.append(fit_rows(sub, args.with_scan_term))
        except ValueError:
            pass

    print("\ncoefficients (cycles per operation)    leave-one-instance-out range")
    for i, n in enumerate(names):
        rng = ("[%10.2f, %10.2f]" % (min(c[i] for c in loo), max(c[i] for c in loo))
               if len(loo) >= 2 else "  n/a: too few instances to leave one out")
        flag = "   <-- NEGATIVE: predictors entangled" if coef[i] < 0 else ""
        print("  %-14s %12.2f        %s%s" % (n, coef[i], rng, flag))

    print("\n%-13s %-10s %-5s %7s %7s  %6s   %s" % (
          "instance", "first", "set", "meas s", "pred s", "err", "share of predicted cycles: " +
          " ".join("%8s" % n for n in names)))
    errs_in, errs_out = [], []
    ghz = statistics.median(r["cycles"] / r["wall"] for r in usable) / 1e9
    for r in usable:
        p = predict(r, coef, args.with_scan_term)
        err = (p - r["cycles"]) / r["cycles"]
        inside = r in train
        (errs_in if inside else errs_out).append(abs(err))
        parts = [c * v / p for c, (_, v) in zip(coef, predictors(r, args.with_scan_term))]
        print("%-13s %-10d %-5s %7.3f %7.3f %+6.1f%%   %s%s" % (
              r["inst"], r["reduce_first"], "train" if inside else "TEST",
              r["cycles"] / ghz / 1e9, p / ghz / 1e9, 100 * err,
              " ".join("%7.0f%%" % (100 * x) for x in parts),
              "   rss %d KB" % r["rss_kb"] if r["rss_kb"] > args.big_rss_kb else ""))

    def summ(label, e):
        if e:
            print("  %-22s median |err| %5.1f%%   max |err| %5.1f%%   (n=%d)" % (
                  label, 100 * statistics.median(e), 100 * max(e), len(e)))
    print("\nfit quality:")
    summ("training runs", errs_in)
    summ("held-out runs", errs_out)
    print("\n(seconds are cycles / %.2f GHz, the median effective clock across runs;"
          " rss flagged above %d KB)" % (ghz, args.big_rss_kb))


def load_csv(path):
    with open(path) as fh:
        return list(csv.DictReader(l for l in fh if not l.startswith("#")))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="mode", required=True)

    c = sub.add_parser("collect", help="run every instance x schedule, write CSV, then fit")
    c.add_argument("--instances", default=",".join(INSTANCES))
    c.add_argument("--repeat", type=int, default=3, help="runs per cell, min cycles kept")
    c.add_argument("--repeat-cutoff", type=float, default=5.0,
                   help="runs slower than this many seconds are done once")
    c.add_argument("--out", help="CSV path (default tests/cost_model.csv)")

    f = sub.add_parser("fit", help="refit an existing CSV")
    f.add_argument("csv")

    for p in (c, f):
        p.add_argument("--train", help="fit only on these families (php,full,rand) and predict the rest")
        p.add_argument("--with-scan-term", action="store_true",
                       help="add decisions*vars, the cost of the linear pick_branch_lit scan")
        p.add_argument("--min-cycles", type=float, default=4e8,
                       help="drop runs below this (default 4e8, about 0.1 s)")
        p.add_argument("--big-rss-kb", type=int, default=16384,
                       help="flag runs whose peak RSS exceeds this (default 16 MB, the P-core L2)")
    args = ap.parse_args()

    rows = collect(args) if args.mode == "collect" else load_csv(args.csv)
    if args.mode == "collect":
        rows = load_csv(args.out or os.path.join(HERE, "cost_model.csv"))
    fit(rows, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
