# Demo inputs — COREP LCR

Fictional sample inputs for a COREP LCR run. All entity data is made up; the
(template, row, column) combinations are real cells from the EBA DPM 2.0 v4.2
release (module `COREP_LCR_DA`), so the data resolves to actual datapoints.

- **`fact_sample.xlsx`** — fact file (`report`, `row`, `column`, `value`).
  Template codes are written in a mix of accepted forms (upstream `C_73_00_a`,
  EBA display `C 74.00.a`, DB `C_76.00.a`) to show normalisation.
- **`indicators_params.xlsx`** — a `parameters` sheet (fictional LEI, reference
  date, base currency, decimals) and a `filing_indicators` sheet.

Regenerate with `python demo/build_demo.py`.
