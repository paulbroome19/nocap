# Sample data — COREP LCR

Documented sample inputs and fixtures for a COREP LCR run. All entity data is
fictional; the (template, row, column) combinations are real cells from the EBA
DPM 2.0 v4.2 release (module `COREP_LCR_DA`), so the data resolves to real
datapoints.

A run **derives** its filing indicators and parameters in-system, so the default
flow needs only a **fact file** (pick an entity + date, upload the fact file,
Run).

## The datasets

1. **`reference_lcr_full.xlsx`** — the **full reference set**. A complete fact
   set engineered so the module's **formula assertions actually evaluate**: it
   populates every closed cell of C_72.00 (Liquid Assets) and C_76.00 (LCR
   calculation) and deliberately mis-sets three cells. The rule register shows
   **52 rules evaluated — 46 satisfied (green), 6 unsatisfied (red)** with real
   comparison detail (e.g. `-450000 >= 0`, `0 = 980000 + 0`,
   `1750000 = 0 - 0 - 0 - 0`). Formula validation runs in ~2 min. This is the
   dataset that proves the formula path end to end.
   Regenerate: `python demo/build_reference_lcr.py` (needs the ingested DPM).

2. **`fact_sample.xlsx`** — the **minimal clean set**. A tiny fact set that
   validates **fully clean** (`generated`, only the `ENTRY_POINT_UNVERIFIED`
   info finding). Template codes are in a mix of accepted forms.

3. **`fact_broken.xlsx`** — the **malformed set** for error-handling. An
   unresolvable cell (`UNRESOLVED_FACT`) and a non-numeric monetary value
   (`DATATYPE_MISMATCH`) → **`failed_validation`**: structural failures in the
   register, with the package still produced and marked not submittable.

Also present: `fact_sample_warnings.xlsx` + `indicators_params.xlsx` (the
advanced indicators/params override), which together surface
`PERCENTAGE_NOT_RATIO` + `EMPTY_FILING_INDICATOR` warnings.

Regenerate the small files with `python demo/build_demo.py`; the full reference
set with `python demo/build_reference_lcr.py`.

> Note: the register lights up (formula rules evaluate) only with the three
> generation fixes — dp{VariableID}, taxonomy container expansion, and
> template-level filing indicators — pinned by
> `backend/tests/validation/test_formula_guard.py` (`pytest -m integration`).
