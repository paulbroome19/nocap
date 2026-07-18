# Demo inputs — COREP LCR

Fictional sample inputs for a COREP LCR run. All entity data is made up; the
(template, row, column) combinations are real cells from the EBA DPM 2.0 v4.2
release (module `COREP_LCR_DA`), so the data resolves to real datapoints.

A run **derives** its filing indicators and parameters in-system, so the default
flow needs only a **fact file** (pick an entity + date, upload the fact file,
Run).

## The acts

1. **`fact_full.xlsx`** — the **hero file** (the "full run"). A fuller fact set
   engineered so the module's **formula assertions actually evaluate**: it
   populates every closed cell of C_72.00 (Liquid Assets) and C_76.00 (LCR
   calculation) and deliberately mis-sets three cells. The rule register shows
   **52 rules evaluated — 46 satisfied (green), 6 unsatisfied (red)** with real
   comparison detail (e.g. `-450000 >= 0`, `0 = 980000 + 0`,
   `1750000 = 0 - 0 - 0 - 0`). Formula validation runs in ~2 min.
   Regenerate: `python demo/build_fact_full.py` (needs the ingested DPM).

2. **`fact_broken.xlsx`** — the "broken run". An unresolvable cell
   (`UNRESOLVED_FACT`) and a non-numeric monetary value (`DATATYPE_MISMATCH`) →
   **`failed_validation`**, i.e. structural failures in the register (the
   package is still produced, marked not submittable).

3. **`fact_sample.xlsx`** — the optional "clean-minimal" file. A tiny set that
   validates **fully clean** (`generated`, only the `ENTRY_POINT_UNVERIFIED`
   info finding). Template codes are in a mix of accepted forms.

Also present: `fact_sample_warnings.xlsx` + `indicators_params.xlsx` (the
advanced indicators/params override), which together surface
`PERCENTAGE_NOT_RATIO` + `EMPTY_FILING_INDICATOR` warnings.

Regenerate the simple files with `python demo/build_demo.py`; the hero file with
`python demo/build_fact_full.py`.

> Note: the register lights up (formula rules evaluate) only with the three
> generation fixes — dp{VariableID}, taxonomy container expansion, and
> template-level filing indicators — pinned by
> `backend/tests/validation/test_formula_guard.py` (`pytest -m integration`).
