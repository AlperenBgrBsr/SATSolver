#!/usr/bin/env python3
"""Memory-layout sweep: same search, growing footprint.

SAT_CLAUSE_PAD=N makes every clause reserve N spare ints. The literals - and
therefore the whole search - are untouched, so every counter must come out
identical to the unpadded run; this script checks that on every row. What
grows is the distance between clauses, so any change in cycles is a memory
effect and nothing else.

Each run is compared against the per-operation cost model of cost_model.py,
refitted here on the runs that stayed inside L2 (peak RSS <= --l2-kb). The
model has never seen a large footprint, so

    excess cycles per visit = (measured - predicted) / clause visits

is the memory cost per visit, in cycles - the number to set against the
latency ladder (tests/latency_ladder.c).

  python3 tests/memory_sweep.py run                    # default instances x pads
  python3 tests/memory_sweep.py run --instances php11_10 --pads 0,64,256,1024
  python3 tests/memory_sweep.py report tests/memory_sweep.csv   # reprint, no solving

Needs: a release build with the visit counters and SAT_CLAUSE_PAD
(cd src && make release), and tests/cost_model.csv from cost_model.py collect.
"""
import argparse
import csv
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cost_model as cm  # noqa: E402

FIELDS = ["inst", "pad", "verdict", "cycles", "instructions", "wall", "rss_kb"] + cm.COUNTERS


def to_numbers(r):
    for k in ["cycles", "instructions", "rss_kb", "pad"] + cm.COUNTERS:
        if k in r and r[k] != "":
            r[k] = int(r[k])
    r["wall"] = float(r["wall"])
    return r


def in_l2_model(path, l2_kb, min_cycles):
    rows = [to_numbers(r) for r in cm.load_csv(path)]
    for r in rows:
        r["reduce_first"] = int(r["reduce_first"])
    use = [r for r in rows if r["cycles"] >= min_cycles and r["rss_kb"] <= l2_kb]
    if len(use) < 8:
        sys.exit("only %d in-L2 runs in %s - run cost_model.py collect first" % (len(use), path))
    coef = cm.fit_rows(use, False)
    print("cost model refitted on %d in-L2 runs (rss <= %d KB) from %s:" % (len(use), l2_kb, path))
    print("  " + "   ".join("%s %.2f" % (n, c) for (n, _), c in
                            zip(cm.predictors(use[0], False), coef)) + "  cycles\n")
    return coef


def run(args):
    if not os.access(cm.SAT, os.X_OK):
        sys.exit("solver not built - run:  cd src && make release")
    out = args.out or os.path.join(HERE, "memory_sweep.csv")
    pads = [int(p) for p in args.pads.split(",")]
    if pads[0] != 0:
        pads = [0] + pads                     # the reference every row is checked against
    rows = []
    with open(out, "w", newline="") as fh:
        for line in cm.header_lines(args):
            fh.write(line + "\n")
        fh.write("# pads: %s\n" % ",".join(map(str, pads)))
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for inst in args.instances.split(","):
            path = os.path.join(cm.BENCH, inst + ".cnf")
            for pad in pads:
                env = {"SAT_CLAUSE_PAD": str(pad)}
                best = cm.run_once(path, env)
                if best["wall"] < args.repeat_cutoff:
                    for _ in range(args.repeat - 1):
                        r = cm.run_once(path, env)
                        if r["cycles"] and r["cycles"] < best["cycles"]:
                            best = r
                row = {"inst": inst, "pad": pad, **best}
                w.writerow({k: row.get(k, "") for k in FIELDS})
                fh.flush()
                rows.append(row)
                print("%-13s pad %5d  %6.2fs  rss %7d KB  IPC %.2f" % (
                      inst, pad, row["wall"], row["rss_kb"],
                      row["instructions"] / max(row["cycles"], 1)), flush=True)
    print("\nwrote %s\n" % out)
    return rows


def report(rows, coef, l2_kb):
    for inst in dict.fromkeys(r["inst"] for r in rows):
        R = [r for r in rows if r["inst"] == inst]
        ref = next((r for r in R if r["pad"] == 0), None)
        print("%s" % inst)
        print("  %5s %9s %9s %9s %6s %8s %10s   %s" % (
              "pad", "rss MB", "est MB", "cyc/visit", "IPC", "model", "excess", "search"))
        print("  %5s %9s %9s %9s %6s %8s %10s   %s" % (
              "", "", "clauses", "", "", "error", "cyc/visit", "identical?"))
        for r in R:
            v = r["clause_visits"]
            pred = cm.predict(r, coef, False)
            # Rough clause footprint at the peak: struct + padded literal block,
            # rounded to malloc's 16-byte quantum. Held-clause length at exit
            # stands in for the average.
            avg_len = r["learnt_lits"] / max(r["learnts"], 1)
            block = ((4 * (avg_len + r["pad"]) + 15) // 16) * 16
            est_mb = r["max_learnts"] * (32 + block + 8) / 2 ** 20
            same = (ref is not None and all(r[k] == ref[k] for k in cm.COUNTERS))
            print("  %5d %9.1f %9.1f %9.2f %6.2f %+7.1f%% %10.2f   %s%s" % (
                  r["pad"], r["rss_kb"] / 1024, est_mb, r["cycles"] / v,
                  r["instructions"] / r["cycles"], 100 * (r["cycles"] - pred) / pred,
                  (r["cycles"] - pred) / v,
                  "yes" if same else "NO - the search changed, discard this row",
                  "   (past L2)" if r["rss_kb"] > l2_kb else ""))
        print()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="mode", required=True)
    r = sub.add_parser("run", help="run instances x pads, write CSV, report")
    r.add_argument("--instances", default="php11_10,rand3_250_s3")
    r.add_argument("--pads", default="0,8,32,128,512,2048")
    r.add_argument("--repeat", type=int, default=3, help="runs per cell, min cycles kept")
    r.add_argument("--repeat-cutoff", type=float, default=5.0)
    r.add_argument("--out", help="CSV path (default tests/memory_sweep.csv)")
    p = sub.add_parser("report", help="reprint the report from an existing CSV")
    p.add_argument("csv")
    for s in (r, p):
        s.add_argument("--model", default=os.path.join(HERE, "cost_model.csv"),
                       help="cost_model.py CSV to fit the in-L2 model from")
        s.add_argument("--l2-kb", type=int, default=16384, help="L2 size in KB (default 16 MB)")
        s.add_argument("--min-cycles", type=float, default=4e8)
    args = ap.parse_args()

    coef = in_l2_model(args.model, args.l2_kb, args.min_cycles)
    if args.mode == "run":
        run(args)
        rows = [to_numbers(x) for x in cm.load_csv(args.out or os.path.join(HERE, "memory_sweep.csv"))]
    else:
        rows = [to_numbers(x) for x in cm.load_csv(args.csv)]
    report(rows, coef, args.l2_kb)
    return 0


if __name__ == "__main__":
    sys.exit(main())
