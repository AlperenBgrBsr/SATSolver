#!/usr/bin/env python3
"""Paired luck test: does a configuration difference survive shuffling?

A deterministic solver gives one sample per formula, and on small hard
instances the heuristics alone can move the conflict count by 2x. This runs
each shuffled copy of one instance (see shuffle_cnf.py) three ways -

  nopre   minisat -no-pre
  pre     minisat           (SatELite preprocessing on)
  sat     ./src/sat

- and compares them per copy, so copy-to-copy difficulty cancels out. Both
minisat runs share -min-learnts, so preprocessing is the only difference
between them.

Reproducible end to end: copies come from fixed seeds through a deterministic
shuffler, the bootstrap uses a fixed RNG seed, and the CSV header records the
command line, git commit, solver build flags and minisat version.

Besides conflicts it records each minisat run's mean learnt-clause length
(minisat's "conflict literals" / conflicts, measured after its clause
minimization), and reports spread both as max/min and as the interquartile
ratio Q3/Q1 - the latter rests on the middle half of the copies rather than on
the two most extreme runs.

  python3 tests/luck_test.py tests/bench/php9_8.cnf --seeds 1-50
  python3 tests/luck_test.py IN.cnf --seeds 1-50 --no-flip --out FILE.csv
  python3 tests/luck_test.py IN.cnf --minisat-flags "-rfirst=2147483647" --tag norestart
  python3 tests/luck_test.py --stats FILE.csv          # recompute, no solving

--minisat-flags is added to BOTH minisat runs, so the pre/no-pre comparison
stays a one-variable comparison. --tag goes into the default CSV name, so a
run with different flags never overwrites an earlier one.

Run from the repo root or anywhere; paths resolve against the repo. Build
./src/sat first (make release for timings; conflicts do not depend on flags).
"""
import argparse
import csv
import math
import os
import random
import re
import shlex
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SAT = os.path.join(ROOT, "src", "sat")
sys.path.insert(0, HERE)
import shuffle_cnf  # noqa: E402

FIELDS = ["seed", "nopre_verdict", "nopre_conf", "nopre_cpu", "nopre_lits", "nopre_clits",
          "pre_verdict", "pre_conf", "pre_cpu", "pre_lits", "pre_clits",
          "sat_verdict", "sat_conf", "sat_sec"]
VERDICT = {10: "SAT", 20: "UNSAT"}
BOOT_SEED = 12345
BOOT_N = 10000


# --- running -----------------------------------------------------------------

def run_minisat(path, pre, min_learnts, cpu_lim, extra):
    args = ["minisat", "-min-learnts=%d" % min_learnts, "-cpu-lim=%d" % cpu_lim] + extra
    if not pre:
        args.append("-no-pre")
    p = subprocess.run(args + [path], capture_output=True, text=True)
    out = p.stdout

    m = re.search(r"^conflicts\s*:\s*(\d+)", out, re.M)
    conf = int(m.group(1)) if m else 0          # absent if solved by simplification
    m = re.search(r"^CPU time\s*:\s*([\d.]+)", out, re.M)
    cpu = float(m.group(1)) if m else float("nan")
    # First row of the search table holds the sizes after simplification.
    m = re.search(r"^\|\s+\d+\s+\|\s+\d+\s+\d+\s+(\d+)\s+\|", out, re.M)
    lits = int(m.group(1)) if m else -1
    # Total literals over all learnt clauses, counted after minimization.
    m = re.search(r"^conflict literals\s*:\s*(\d+)", out, re.M)
    clits = int(m.group(1)) if m else 0

    verdict = VERDICT.get(p.returncode, "TIMEOUT" if "INDETERMINATE" in out else
                          "rc=%d" % p.returncode)
    return verdict, conf, cpu, lits, clits


def run_sat(path, timeout):
    t0 = time.perf_counter()
    try:
        p = subprocess.run([SAT, path], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "TIMEOUT", 0, float(timeout)
    dt = time.perf_counter() - t0
    m = re.search(r"^c conflicts\s+(\d+)", p.stdout, re.M)
    return VERDICT.get(p.returncode, "rc=%d" % p.returncode), int(m.group(1)) if m else 0, dt


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
    mver = cmd(["minisat", "--help"])
    mver = next((l for l in mver.splitlines() if "minisat" in l.lower()), "minisat")
    return [
        "# luck_test.py " + " ".join(sys.argv[1:]),
        "# generated %s" % time.strftime("%Y-%m-%d %H:%M:%S"),
        "# git %s%s" % (cmd(["git", "rev-parse", "--short", "HEAD"]),
                        " (dirty)" if cmd(["git", "status", "--porcelain", "--untracked-files=no"]) else ""),
        "# sat build: %s" % build,
        "# minisat: %s (%s)" % (cmd(["which", "minisat"]), mver),
        "# minisat flags: -min-learnts=%d -cpu-lim=%d %s" % (args.min_learnts, args.cpu_lim,
                                                             args.minisat_flags),
        "# shuffle: flip=%s" % (not args.no_flip),
        "# bootstrap: %d resamples, rng seed %d" % (BOOT_N, BOOT_SEED),
    ]


def solve_all(args):
    seeds = shuffle_cnf.parse_seeds(args.seeds)
    nvars, clauses = shuffle_cnf.read_cnf(args.cnf)
    name = os.path.splitext(os.path.basename(args.cnf))[0]
    tag = "n" if args.no_flip else "s"
    outdir = os.path.join(ROOT, "tests", "shuffled")
    os.makedirs(outdir, exist_ok=True)

    extra = shlex.split(args.minisat_flags)
    out = args.out or os.path.join(ROOT, "tests", "shuffled", "%s.luck-%s%s.csv" % (
        name, "noflip" if args.no_flip else "flip", "-" + args.tag if args.tag else ""))
    rows = []
    with open(out, "w", newline="") as fh:
        for line in header_lines(args):
            fh.write(line + "\n")
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()

        print("%5s %12s %12s %8s %10s   lits(no/pre)  learnt len(no/pre)" % (
              "seed", "nopre", "pre", "pre/no", "sat"))
        for seed in seeds:
            # Always regenerated: the shuffler is deterministic, so this is the
            # same file every time and a stale copy can never sneak in.
            path = os.path.join(outdir, "%s.%s%d.cnf" % (name, tag, seed))
            shuffled = shuffle_cnf.shuffle(nvars, clauses, seed, not args.no_flip)
            with open(path, "w") as f:
                f.write("c shuffled copy of %s, seed %d, flip=%s\n"
                        % (os.path.basename(args.cnf), seed, not args.no_flip))
                f.write("p cnf %d %d\n" % (nvars, len(shuffled)))
                for c in shuffled:
                    f.write(" ".join(map(str, c)) + " 0\n")

            a = run_minisat(path, False, args.min_learnts, args.cpu_lim, extra)
            b = run_minisat(path, True, args.min_learnts, args.cpu_lim, extra)
            c = run_sat(path, args.cpu_lim)
            row = dict(zip(FIELDS, [seed, *a, *b, *c]))
            w.writerow(row); fh.flush()
            rows.append(row)

            verdicts = {a[0], b[0], c[0]} - {"TIMEOUT"}
            flag = "   <-- VERDICT MISMATCH" if len(verdicts) > 1 else ""
            ratio = b[1] / a[1] if a[1] else float("nan")
            print("%5d %12d %12d %8.2f %10d   %d/%-6d %7.1f/%.1f%s" % (
                  seed, a[1], b[1], ratio, c[1], a[3], b[3],
                  a[4] / a[1] if a[1] else 0, b[4] / b[1] if b[1] else 0, flag), flush=True)
    print("\nwrote %s" % out)
    return rows


# --- statistics --------------------------------------------------------------

def sign_test(diffs):
    """Exact two-sided sign test. Zeros are dropped."""
    d = [x for x in diffs if x != 0]
    n, k = len(d), sum(1 for x in d if x > 0)
    if n == 0:
        return n, k, 1.0
    tail = sum(math.comb(n, i) for i in range(min(k, n - k) + 1)) / 2 ** n
    return n, k, min(1.0, 2 * tail)


def wilcoxon(diffs):
    """Two-sided Wilcoxon signed-rank, normal approximation with tie and
    continuity correction. Fine for n >= ~20; treat smaller n with care."""
    d = [x for x in diffs if x != 0]
    n = len(d)
    if n == 0:
        return float("nan"), 1.0
    order = sorted(range(n), key=lambda i: abs(d[i]))
    ranks = [0.0] * n
    ties = 0.0
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(d[order[j + 1]]) == abs(d[order[i]]):
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        t = j - i + 1
        ties += t ** 3 - t
        i = j + 1
    w_plus = sum(r for r, x in zip(ranks, d) if x > 0)
    mean = n * (n + 1) / 4
    var = n * (n + 1) * (2 * n + 1) / 24 - ties / 48
    if var <= 0:
        return w_plus, 1.0
    z = (abs(w_plus - mean) - 0.5) / math.sqrt(var)
    p = 2 * (1 - statistics.NormalDist().cdf(max(z, 0.0)))
    return w_plus, p


def bootstrap_median_ci(xs):
    rng = random.Random(BOOT_SEED)
    meds = sorted(statistics.median(rng.choices(xs, k=len(xs))) for _ in range(BOOT_N))
    return meds[int(0.025 * BOOT_N)], meds[int(0.975 * BOOT_N) - 1]


def compare(rows, num, den, label, metric=None):
    metric = metric or conflicts
    """Per-copy ratio num/den of `metric`. Above 1 means `num` is larger."""
    pairs = []
    for r in rows:
        if r[num + "_verdict"] == "TIMEOUT" or r[den + "_verdict"] == "TIMEOUT":
            continue
        a, b = metric(r, num), metric(r, den)
        if a is not None and b is not None and a > 0 and b > 0:
            pairs.append((a, b))
    dropped = len(rows) - len(pairs)
    if not pairs:
        print("%s: no usable pairs" % label)
        return
    ratios = [a / b for a, b in pairs]
    logs = [math.log(x) for x in ratios]
    n, k, p_sign = sign_test(logs)
    _, p_wil = wilcoxon(logs)
    lo, hi = bootstrap_median_ci(ratios)

    print("\n%s  (n=%d%s)" % (label, len(pairs),
          ", %d dropped: timeout or no data" % dropped if dropped else ""))
    print("  median ratio        %.3f   95%% bootstrap CI [%.3f, %.3f]" % (statistics.median(ratios), lo, hi))
    print("  geometric mean      %.3f" % math.exp(statistics.mean(logs)))
    print("  range               %.3f .. %.3f" % (min(ratios), max(ratios)))
    print("  ratio > 1 in        %d / %d" % (k, n))
    print("  sign test           p = %.3g   (exact, two-sided)" % p_sign)
    print("  Wilcoxon on log     p = %.3g   (normal approx, two-sided)" % p_wil)


def conflicts(r, who):
    return int(r[who + "_conf"])


def learnt_len(r, who):
    """Mean learnt-clause length after minimization. minisat runs only; None
    for ./sat and for CSVs written before the column existed."""
    clits, conf = r.get(who + "_clits"), int(r[who + "_conf"])
    if not clits or conf == 0:
        return None
    return int(clits) / conf


def spread(rows, who, label):
    v = sorted(int(r[who + "_conf"]) for r in rows if r[who + "_verdict"] != "TIMEOUT")
    if not v:
        return
    # Q3/Q1 is the robust one: max/min with 50 copies hangs on two runs.
    iqr = ("%.2f" % (lambda q: q[2] / q[0])(statistics.quantiles(v, n=4))) if len(v) >= 4 else "-"
    print("  %-15s median %9.0f   min %8d   max %8d   max/min %5.2f   Q3/Q1 %s" % (
          label, statistics.median(v), v[0], v[-1], v[-1] / max(v[0], 1), iqr))


def report(rows):
    print("\nconflicts per configuration across copies (how big luck is):")
    spread(rows, "nopre", "minisat -no-pre")
    spread(rows, "pre", "minisat")
    spread(rows, "sat", "./sat")
    compare(rows, "pre", "nopre", "preprocessing effect: minisat / minisat -no-pre")
    compare(rows, "nopre", "sat", "solver gap: minisat -no-pre / ./sat")
    if any(r.get("pre_clits") for r in rows):
        compare(rows, "pre", "nopre",
                "learnt clause length (after minimization): minisat / minisat -no-pre",
                metric=learnt_len)
        for who, label in [("nopre", "minisat -no-pre"), ("pre", "minisat")]:
            v = [x for x in (learnt_len(r, who) for r in rows) if x is not None]
            if v:
                print("  %-15s mean learnt length: median over copies %.2f" % (
                      label, statistics.median(v)))

    bad = [r["seed"] for r in rows
           if len({r["nopre_verdict"], r["pre_verdict"], r["sat_verdict"]} - {"TIMEOUT"}) > 1]
    if bad:
        print("\nWARNING: verdicts disagree on seeds %s - fix that before reading anything above"
              % ", ".join(map(str, bad)))


def load_csv(path):
    with open(path) as fh:
        lines = [l for l in fh if not l.startswith("#")]
    return list(csv.DictReader(lines))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cnf", nargs="?")
    ap.add_argument("--seeds", default="1-50", help="e.g. 1-50 or 1,4,7 (default 1-50)")
    ap.add_argument("--no-flip", action="store_true", help="shuffle without sign flips")
    ap.add_argument("--min-learnts", type=int, default=20000)
    ap.add_argument("--cpu-lim", type=int, default=300, help="seconds per solver run")
    ap.add_argument("--minisat-flags", default="",
                    help='extra flags for both minisat runs, e.g. "-rfirst=2147483647"')
    ap.add_argument("--tag", default="", help="suffix for the default CSV name")
    ap.add_argument("--out", help="CSV path (default tests/shuffled/<name>.luck-<flip|noflip>[-tag].csv)")
    ap.add_argument("--stats", metavar="CSV", help="recompute statistics from an existing CSV")

    # argparse reads a value starting with '-' as a new option, so
    # `--minisat-flags "-rfirst=..."` would fail. Glue the value on with '='.
    argv, rest = [], sys.argv[1:]
    while rest:
        a = rest.pop(0)
        if a == "--minisat-flags" and rest:
            a = "--minisat-flags=" + rest.pop(0)
        argv.append(a)
    args = ap.parse_args(argv)

    if args.stats:
        report(load_csv(args.stats))
        return 0
    if not args.cnf:
        ap.error("give a CNF, or --stats CSV")
    if not os.access(SAT, os.X_OK):
        sys.exit("solver not built - run:  cd src && make release")

    report(solve_all(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
