#!/usr/bin/env python3
"""Benchmark harness: run ./src/sat over tests/bench and record the numbers
clause deletion is supposed to move.

Reports, per instance: verdict, wall time, peak RSS, and the solver's own `c`
counters. Instances that exceed the timeout are reported as TIMEOUT and still
listed - a baseline that hides the hard cases is not a baseline.

  python3 tests/bench.py [--timeout SECONDS] [--out FILE] [pattern ...]

Environment passed through to the solver (SAT_REDUCE_FIRST, SAT_REDUCE_INC,
SAT_CHECK_EVERY) is recorded in the header so a run is self-describing.
"""
import argparse
import glob
import os
import re
import signal
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(os.path.join(__file__, "..")))
SAT = os.path.join(ROOT, "src", "sat")
BENCH = os.path.join(ROOT, "tests", "bench")

FIELDS = ["conflicts", "decisions", "propagations", "clause_visits",
          "learnts_total", "learnts", "max_learnts", "learnt_lits",
          "reduces", "deleted"]


def run_one(path, timeout):
    """Returns (verdict, seconds, peak_rss_bytes, stats dict)."""
    t0 = time.time()
    proc = subprocess.Popen(["/usr/bin/time", "-l", SAT, path],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, start_new_session=True)
    try:
        out, err = proc.communicate(timeout=timeout)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.communicate()
        return "TIMEOUT", timeout, 0, {}

    secs = time.time() - t0
    verdict = {10: "SAT", 20: "UNSAT"}.get(rc, "rc=%d" % rc)

    stats = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0] == "c" and parts[1] in FIELDS:
            stats[parts[1]] = int(parts[2])

    rss = 0
    m = re.search(r"(\d+)\s+maximum resident set size", err)
    if m:
        rss = int(m.group(1))

    return verdict, secs, rss, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--out", default=None)
    ap.add_argument("--note", default="", help="recorded in the output header")
    ap.add_argument("--repeat", type=int, default=3,
                    help="runs per instance; the fastest is reported. Counters are "
                         "deterministic, so only the timing benefits. Instances slower "
                         "than --repeat-cutoff seconds are run once.")
    ap.add_argument("--repeat-cutoff", type=float, default=5.0)
    ap.add_argument("patterns", nargs="*", default=None)
    args = ap.parse_args()

    if not os.access(SAT, os.X_OK):
        print("solver not built - run:  cd src && make release")
        return 1

    pats = args.patterns or [os.path.join(BENCH, "*.cnf")]
    files = []
    for p in pats:
        files.extend(glob.glob(p))
    files = sorted(set(files))

    if not files:
        print("no instances matched")
        return 1

    lines = []
    lines.append("# solver baseline")
    lines.append("# generated %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    lines.append("# timeout %gs" % args.timeout)
    if args.note:
        lines.append("# %s" % args.note)
    for k in ("SAT_REDUCE_FIRST", "SAT_REDUCE_INC", "SAT_CHECK_EVERY"):
        lines.append("# %s=%s" % (k, os.environ.get(k, "(default)")))
    lines.append("")
    hdr = "%-20s %-7s %8s %9s %10s %10s %12s %13s %11s %8s %8s" % (
        "instance", "verdict", "sec", "rss_kb", "conflicts", "decisions",
        "clause_vis", "max_learnts", "learnt_lit", "reduces", "deleted")
    lines.append(hdr)
    lines.append("-" * len(hdr))

    for f in files:
        # First run pays for page-cache warming and can be an order of magnitude
        # slow on the small instances, which would swamp any before/after delta.
        verdict, secs, rss, st = run_one(f, args.timeout)
        if verdict != "TIMEOUT" and secs < args.repeat_cutoff:
            for _ in range(max(0, args.repeat - 1)):
                v2, s2, r2, st2 = run_one(f, args.timeout)
                if v2 != verdict:
                    print("  WARNING: %s gave %s then %s" % (f, verdict, v2))
                secs = min(secs, s2)
                rss = max(rss, r2)
        lines.append("%-20s %-7s %8.2f %9d %10s %10s %12s %13s %11s %8s %8s" % (
            os.path.basename(f), verdict, secs, rss // 1024,
            st.get("conflicts", "-"), st.get("decisions", "-"),
            st.get("clause_visits", "-"), st.get("max_learnts", "-"),
            st.get("learnt_lits", "-"), st.get("reduces", "-"),
            st.get("deleted", "-")))
        print(lines[-1], flush=True)

    text = "\n".join(lines) + "\n"
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(text)
        print("\nwrote %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
