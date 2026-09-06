# SAT Solver

A CDCL (Conflict-Driven Clause Learning) SAT solver written from scratch in C++17,
with no external dependencies.

Given a Boolean formula in CNF, it decides whether a satisfying assignment exists
and produces one if it does.

## Status

**Implemented**

- Two-watched-literal unit propagation
- 1UIP conflict analysis with clause learning
- Non-chronological backjumping
- VSIDS branching, with activity decay and rescaling
- Phase saving
- DIMACS CNF parsing

**Not yet implemented**

- **Clause deletion** — learnt clauses currently accumulate without bound, which
  is the main thing preventing this from scaling to large instances
- Restarts
- Preprocessing and inprocessing

This is a learning project. It is correct, and it is not fast.

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
false. UNSAT prints `s UNSATISFIABLE` and no model.

Exit codes: **10** satisfiable, **20** unsatisfiable, **1** usage error.

## Testing

```bash
cd src
make test               # regression suite: verdicts plus model verification
make fuzz && ./fuzz     # differential fuzzing against exhaustive brute force
```

`make test` runs every instance under `tests/`, checks the verdict, and for each
SAT answer independently re-reads the CNF and verifies the reported model. It
never trusts the solver's own state.

`./fuzz [instances] [start_seed]` generates random 3-SAT (4–14 variables, clause
ratio 3.0–6.0, straddling the 4.26 phase transition) and checks each verdict
against exhaustive brute force, which is an exact oracle at that size. On a
mismatch it writes `fuzz-fail-<seed>.cnf` and prints the seed, so any failure is
reproducible. Exit code 1 means at least one disagreement.

Current state: **1010 regression instances and 15,000 fuzzed instances, zero
mismatches**, clean under UBSan and libc++ hardening.

### Benchmark set

`tests/uf20-91/` holds 1000 uniform random 3-SAT instances (20 variables,
91 clauses, all satisfiable) from
[SATLIB](https://www.cs.ubc.ca/~hoos/SATLIB/benchm.html), redistributed
unmodified so the suite runs from a fresh clone. They are not covered by this
project's licence — see [tests/uf20-91/SOURCE.md](tests/uf20-91/SOURCE.md).

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

## Layout

```
src/
  SATSolver.hpp   solver interface and state
  SATSolver.cpp   propagation, conflict analysis, search
  main.cpp        CLI
  fuzz.cpp        differential fuzzer
  Makefile
tests/
  run_tests.py    regression runner with independent model verification
  sat/            satisfiable edge cases
  unsat/          unsatisfiable instances
  uf20-91/        SATLIB benchmark set, 1000 satisfiable instances
```

## References

- Eén & Sörensson, *An Extensible SAT-solver* (2003) — the MiniSat paper
- Marques-Silva & Sakallah, *GRASP: A Search Algorithm for Propositional
  Satisfiability* (1999) — conflict-driven learning
- Audemard & Simon, *Predicting Learnt Clauses Quality in Modern SAT Solvers*
  (2009) — LBD, the basis for the clause deletion still to be added

## License

MIT — see [LICENSE](LICENSE).
