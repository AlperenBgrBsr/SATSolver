# Performance report

LaTeX source for the full report (`main.tex`) and the one-page summary
(`summary.tex`). Written for Overleaf; it also builds locally.

## Layout

| path | what | edit? |
|---|---|---|
| `main.tex`, `summary.tex` | the two documents | yes |
| `sections/*.tex` | one file per section, with `% POINTS TO MAKE` notes and red `\TODO`s | yes, this is the writing |
| `figures/*.tex` | pgfplots figures, drawn from `data/` | only for styling |
| `refs.bib` | references, check them before submitting | yes |
| `preamble.tex` | shared packages and macros | rarely |
| `data/`, `tables/`, `numbers.tex` | **generated** by `make_data.py` | **no**, regenerate instead |
| `make_data.py` | turns `tests/*.csv` and the profiles into the above | when adding a figure |

Every experimental number in the text should be a macro from `numbers.tex`
(e.g. `\numCoefSearch`, `\numModelMedianErr`), not typed by hand. Then a rerun
of an experiment, followed by `make_data.py`, updates the report with no edits.

## Overleaf

1. Run `python3 docs/report/make_data.py` locally (needs the CSVs under `tests/`
   and the profiles under `src/` and `prof/`).
2. Zip `docs/report/` and upload it: Overleaf → New Project → Upload Project.
3. Set the main document to `main.tex` (Menu → Main document). For the one-pager,
   switch it to `summary.tex`.

## Locally

```bash
cd docs/report
pdflatex main && bibtex main && pdflatex main && pdflatex main
```

Without `pgfplots` installed (a minimal TeX Live), the figures compile to
labelled placeholder boxes; everything else builds normally.
