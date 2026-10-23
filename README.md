# SAT Solver

A CDCL (Conflict-Driven Clause Learning) SAT solver written from scratch in C++17,
with no external dependencies, together with a measurement study of where its
time goes and why.

Given a Boolean formula in CNF, it decides whether a satisfying assignment exists
and produces one if it does. Every answer is checked independently: models
against the formula on disk, unsatisfiability by a DRAT proof verified with
`drat-trim`.

## Performance study: summary

**Full report: [docs/report/performance-report.pdf](docs/report/performance-report.pdf)**
(9 pages: methods, every table and figure, reproduction commands). One-page
version: [docs/report/summary.pdf](docs/report/summary.pdf). The LaTeX source,
with every figure drawn from the raw data, is in [docs/report/](docs/report).

Measured on an Apple M3 Pro. Every number below comes from a script in
[`tests/`](tests) with fixed seeds, and each run records its git commit, build
flags and machine.

- **Where the time goes.** 93% of runtime is unit propagation. Half of the whole
  run is spent searching for a replacement watched literal, and most of that
  sits at the exit of the search loop. That pattern indicates a mispredicted,
  data-dependent branch rather than slow memory.
- **A four-number cost model.** Cycles ≈ 6.0 per clause visit that finds the
  clause already satisfied + 86.8 per replacement search + 2.1 per literal
  scanned + about 4,200 per conflict. It predicts total cycles with a median
  error of 2.5% over 39 runs, across three instance families and four clause
  deletion schedules (0.1 s to 26 s).
- **A headline result that did not survive control.** A single run made the
  solver look 12× faster than MiniSat on `php11_10`. Splitting runtime into
  conflicts × cost per conflict showed why: MiniSat's learnt-clause limit,
  sized from the formula, forced 42× more conflicts. Its conflicts were 3.5×
  cheaper, but only because it kept so few clauses; given a database at least
  as large as this solver's, it was 6× slower per conflict. Over 50 shuffled copies of `php9_8`, the comparison
  depends on literal polarity alone (1.51× ahead against 0.78× behind). With
  restarts and clause minimization switched off in MiniSat, the two solvers
  become statistically indistinguishable (conflict ratio 1.06, 95% CI
  [0.96, 1.12]). The gap is exactly those two features.
- **Memory, measured with the search held fixed.** Reserving unused space in
  every clause leaves the search unchanged and grows the memory footprint 20×.
  That raises the cost per clause visit by 23%. The cost stays flat while the
  data fits in the 16 MB L2 cache. The extra cycles appear only in code that
  reads the padded clause data; code that does not read it is unaffected.
- **Trust has a price, and it is small.** Every UNSAT verdict is
  proof-checked. Writing the proof costs 11–23% extra cycles. Checking it takes
  0.7–1.5× the solve time on the pigeonhole and random families.

Limits: one machine; instances of at most 250 variables, almost all fitting in
L2; and no hardware performance counters on this setup, so the cache and
branch attributions are inferred from several independent measurements rather
than counted.

## Status

**Implemented**

- Two-watched-literal unit propagation
- 1UIP conflict analysis with clause learning
- Non-chronological backjumping
- VSIDS branching, with activity decay and rescaling
- Phase saving
- Clause deletion by LBD (literal block distance), computed during conflict
  analysis
- DRAT proof output, so UNSAT answers can be checked independently
- Built-in counters, an invariant checker, and knobs for measurement runs
- DIMACS CNF parsing

**Not yet implemented**, in planned order: restarts, clause minimization,
blocking literals, a VSIDS heap, arena clause storage, and preprocessing. The
study above gives a measured expectation for most of them.

## Build

```bash
cd src
make            # builds ./sat
```

Requires a C++17 compiler. Other targets:

| target | purpose |
|---|---|
| `make check` | build with UBSan and libc++ hardening — use this while developing |
| `make test` | run the regression suite |
| `make fuzz` | build the differential fuzzer |
| `make release` | `-O2 -DNDEBUG`, for timing runs |
| `make bench-gen` | generate the benchmark instances into `tests/bench/` |
| `make clean` | remove build artifacts |

Objects are rebuilt automatically when the flag set changes, so switching between
`make` and `make check` never links mismatched objects.

### macOS note

If a plain `clang++` fails inside `<iostream>` with `use of undeclared identifier
'__builtin_ctzg'`, your Command Line Tools ship a libc++ newer than your compiler
supports. The Makefile detects an installed Xcode SDK and passes `-isysroot`
automatically; override with `make SDK=/path/to/sdk` or disable with `make SDK=`.

## Usage

```bash
./sat instance.cnf
```

Output follows the DIMACS competition convention:

```
$ ./sat ../tests/uf20-91/uf20-01.cnf
s SATISFIABLE
v -1 2 3 4 -5 -6 -7 8 9 10 11 -12 -13 14 15 -16 17 18 19 20 0
```

A positive literal on the `v` line means the variable is true, negative means
false. UNSAT prints `s UNSATISFIABLE` and no model. Solver counters are printed
as `c` lines before the `s` line.

Exit codes: **10** satisfiable, **20** unsatisfiable, **1** usage error.

To get a checkable proof of unsatisfiability:

```bash
SAT_PROOF=proof.drat ./sat instance.cnf
drat-trim instance.cnf proof.drat        # prints "s VERIFIED"
```

Other environment variables: `SAT_REDUCE_FIRST` / `SAT_REDUCE_INC` set the
clause-deletion schedule, `SAT_CHECK_EVERY` runs the invariant checker every N
iterations, `SAT_LOG_REDUCES` logs each deletion pass, and `SAT_CLAUSE_PAD`
reserves spare space per clause for memory experiments.

## Testing

```bash
cd src
make test               # regression suite: verdicts, models and UNSAT proofs
make fuzz && ./fuzz     # differential fuzzing against exhaustive brute force
```

`make test` runs every instance under `tests/` and checks the verdict. For each
SAT answer it re-reads the CNF and verifies the reported model; for each UNSAT
answer it solves again with proof logging on and has `drat-trim` check the
proof. It never trusts the solver's own state. `drat-trim` is found via
`$DRAT_TRIM`, then `PATH`, then a checkout beside this repository; without it
the proof step is skipped with a notice.

`./fuzz [instances] [start_seed]` generates random 3-SAT (4–14 variables, clause
ratio 3.0–6.0, straddling the 4.26 phase transition) and checks each verdict
against exhaustive brute force, which is an exact oracle at that size. On a
mismatch it writes `fuzz-fail-<seed>.cnf` and prints the seed, so any failure is
reproducible. Exit code 1 means at least one disagreement.

Current state: **1010 regression instances and 15,000 fuzzed instances, zero
mismatches**, clean under UBSan and libc++ hardening. The fuzz run is repeated
with `SAT_REDUCE_FIRST=10 SAT_REDUCE_INC=5`: fuzz instances are random 3-SAT
with at most 14 variables, which rarely if ever reach the default 2,000-conflict
threshold, so without it the fuzzer would barely test clause deletion.

### Benchmark set

`tests/uf20-91/` holds 1000 uniform random 3-SAT instances (20 variables,
91 clauses, all satisfiable) from
[SATLIB](https://www.cs.ubc.ca/~hoos/SATLIB/benchm.html), redistributed
unmodified so the suite runs from a fresh clone. They are not covered by this
project's licence — see [tests/uf20-91/SOURCE.md](tests/uf20-91/SOURCE.md).

The performance instances (pigeonhole, every-sign-combination and random 3-SAT
at up to 250 variables) are generated by `make bench-gen` rather than stored.

## Reproducing the performance study

Build with `make release` first. Each script writes a CSV whose header records
the configuration it ran under.

| script | what it measures |
|---|---|
| `tests/bench.py` | runtime, memory and counters over the benchmark set |
| `tests/cost_model.py` | fits and validates the per-operation cycle model |
| `tests/luck_test.py` | paired comparison against MiniSat over shuffled copies |
| `tests/shuffle_cnf.py` | satisfiability-preserving shuffled copies of an instance |
| `tests/memory_sweep.py` | cost per clause visit as the footprint grows, search fixed |
| `tests/latency_ladder.c` | this machine's L1 / L2 / DRAM load latencies |
| `tests/proof_cost.py` | proof logging overhead and `drat-trim` checking time |
| `tests/proof_complexity.py` | growth on pigeonhole against the fullN family |

## How it works

**Literal encoding.** Variables are 0-indexed internally. A literal is `2*var`
when positive and `2*var + 1` when negative, so `lit >> 1` is the variable,
`lit & 1` is the sign, and `lit ^ 1` is the negation — negation is a single XOR.

**Two watched literals.** Each clause watches two of its literals, always held in
`lits[0]` and `lits[1]`. A clause only needs attention when a watched literal
becomes false, so `propagate` visits just `watches[lit ^ 1]` and ignores the vast
majority of the database on each assignment.

**Trail.** `trail` is the stack of literals made true in assignment order.
`trail_lim` records its length at each decision level, `reason[var]` is the clause
that forced a variable (`-1` for a decision), and together these form the
implication graph.

**Conflict analysis.** On a conflict, `analyze` walks the trail backwards,
repeatedly replacing a forced literal with the literals of the clause that forced
it, until exactly one literal from the current decision level remains — the first
unique implication point. The resulting clause is added to the database, and the
solver backjumps to the second-highest decision level in it, where the clause is
unit and immediately forces an assignment. Every conflict therefore makes forward
progress rather than merely undoing work.

**Clause deletion.** Each learnt clause records its LBD, the number of distinct
decision levels among its literals, measured during conflict analysis because a
backjump erases exactly the levels it is made of. Periodically, the solver
deletes half of the deletable learnt clauses, worst LBD first. Clauses that are
currently the reason for an assignment, and clauses with LBD ≤ 2, are kept.
Clause indices then shift, so watch lists are rebuilt and reasons remapped.

**Proofs.** With `SAT_PROOF` set, every learnt clause is written as a DRAT
addition and every deleted clause as a deletion, ending with the empty clause.
Each learnt clause follows by unit propagation from the formula plus the clauses
learnt before it, so the checker can verify every step in order.

## Layout

```
src/
  SATSolver.hpp   solver interface and state
  SATSolver.cpp   propagation, conflict analysis, clause deletion, search
  DRAT.hpp/.cpp   proof output
  main.cpp        CLI
  fuzz.cpp        differential fuzzer
  Makefile
tests/
  run_tests.py    regression runner with independent model and proof checking
  gen_bench.py    generates the performance instances
  *.py, *.c       performance study scripts (see above)
  sat/            satisfiable edge cases
  unsat/          unsatisfiable instances
  uf20-91/        SATLIB benchmark set, 1000 satisfiable instances
```

## References

- Eén & Sörensson, *An Extensible SAT-solver* (2003) — the MiniSat paper
- Marques-Silva & Sakallah, *GRASP: A Search Algorithm for Propositional
  Satisfiability* (1999) — conflict-driven learning
- Audemard & Simon, *Predicting Learnt Clauses Quality in Modern SAT Solvers*
  (2009) — LBD, the basis for the clause deletion
- Wetzler, Heule & Hunt, *DRAT-trim: Efficient Checking and Trimming Using
  Expressive Clausal Proofs* (2014) — the proof format and checker
- Haken, *The Intractability of Resolution* (1985) — why pigeonhole formulas are
  exponentially hard for every resolution-based solver

## License

MIT — see [LICENSE](LICENSE).
