# Arelle formula validation — notes

Reference for the `validation/arelle_adapter.py` (v2 formula phase). Findings
from the feasibility spike (`arelle-release 2.42.1`).

## What works (proven offline)
- **Offline taxonomy load** via taxonomy-package **catalog remapping**: register
  the EBA packages (`PackageManager.addPackage` / CLI `--packages`, repeated per
  package) → entry-point URLs resolve to local files inside the package zips. No
  network for `eba.europa.eu` URLs.
- **Load + validate** an EBA xBRL-CSV package: pass the **report-package zip** with
  `--reportPackage` (Arelle loads `reports/report.json`).
- **Formula execution** produces rule-level results: each unsatisfied assertion is
  a structured log record
  `code=message:v16053_m_0, level=warning, message="v16053_m_0: {D_02.00.a,0060,0100,} >= … Fails because …"`.
  → `code` = rule id (`v16053_m`), `level` = severity, message carries the
  expression + `{TEMPLATE,ROW,COL,}` cell refs (→ location). Rule linkbases are
  `…/val/vr-vNNNN_m.xml`; severity + deactivations are in the Severity package
  (`*-val-severity.xml`, `*-ignore-val.xml`).

Timing (spike, offline): a small module (IRRBBDIS) loads+validates in ~15s;
ESG (many rules, random data → 1,862 unsatisfied) ran fully offline in ~75s.
**Load/parse dominates** → run off the request path and reuse a warm process.

## The offline dependency gap (why eurofiling is vendored)
The EBA taxonomy **imports `eurofiling.info` core files it does not bundle**
(`ext/model.xsd`, `func/func.xsd`, `error-formatting.xml`,
`interval-arithmetics.xml`, `math.xml`, `filing-indicators.xsd`, …). Without them
the taxonomy is incomplete and loading fails offline. They are **vendored** in
`backend/app/validation/vendor/eurofiling/` (a taxonomy-package layout with a
catalog remapping `http://www.eurofiling.info/` → the local files). The adapter
zips them at runtime and passes the zip as an extra `--packages`, so validation
is **fully offline with zero external state** (verified: 0 errors, 1,862
assertions, no Arelle cache).

## Version pinning (per-release artifact)
The provided package is **DPM 4.1 and partial** (ESG/MICA/PAY/PILLAR3 — **no
COREP**); our generated packages declare **4.2 COREP** entry points. A taxonomy
package must **match the package's declared version + framework**. Design: the
taxonomy package is a **per-release artifact** dropped into the snapshot's slot
**`{DATA_DIR}/snapshots/<id>/taxonomy/*.zip`** and loaded per snapshot —
consistent with sealed snapshots. If the package doesn't match, Arelle fails to
load; the adapter detects this (`oime:invalidTaxonomy` /
`xbrlce:unresolvableBaseMetadataFile`) and emits a non-blocking
`FORMULA_VALIDATION_UNAVAILABLE` finding rather than a false clean pass.

## Adapter shape
- Interface `FormulaValidator`; `ArelleFormulaValidator.validate(package, taxo_pkgs)`.
- Runs Arelle offline (`--formula run`), captures `logToBuffer` → `getJson()`,
  maps `message:v…` records → `Finding` (severity=level, code=rule id,
  message=text, location=`{TEMPLATE,ROW,COL}`), collapsing per-fact instances to
  one finding per rule and dropping deactivated rules.
- **Never crashes a run**: Arelle missing / errored / mismatched → one info/warning
  finding. Runs as the background **`formula`** phase after structural
  (`formula_validation_running` → finalise). Structural stays independent.
- Deactivated rules: config list seeded with `v6272_m`, `v23336_m`
  (`load_deactivated_rules`) + seam for the full spreadsheet.
- Feature flag `ARELLE_ENABLED`; disabled ⇒ formula phase skipped.
