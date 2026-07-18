# Demo inputs — COREP LCR

Fictional sample inputs for a COREP LCR run. All entity data is made up; the
(template, row, column) combinations are real cells from the EBA DPM 2.0 v4.2
release (module `COREP_LCR_DA`), so the data resolves to real datapoints.

A run **derives** its filing indicators and parameters in-system, so the default
flow needs only a **fact file** (pick an entity + date, upload the fact file,
Run). `indicators_params.xlsx` is the optional **"advanced" override**.

## Three acts

1. **`fact_sample.xlsx`** — the golden file. Validates **fully clean**
   (`generated`, only the `ENTRY_POINT_UNVERIFIED` info finding). Template codes
   are in a mix of accepted forms (upstream `C_73_00_a`, EBA `C 74.00.a`, DB
   `C_76.00.a`).
2. **`fact_sample_warnings.xlsx`** — a percentage reported as `1.45` (not a
   ratio) → `PERCENTAGE_NOT_RATIO`. Upload it **together with the advanced
   override** `indicators_params.xlsx` (which flags `C_72.00.a` as reported
   though it has no facts) to also get `EMPTY_FILING_INDICATOR`. Still
   `generated` (warnings only).
3. **`fact_broken.xlsx`** — an unresolvable cell (`UNRESOLVED_FACT`) and a
   non-numeric monetary value (`DATATYPE_MISMATCH`) → **`failed_validation`**
   (the package is still produced, marked not submittable).

Regenerate with `python demo/build_demo.py`.
