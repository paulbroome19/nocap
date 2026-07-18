# xBRL-CSV report package — notes

Reference material for the generation stage. Sources (untracked, in
`docs/reference/`):

- **`eba_filing_rules_v5.7_2025_11_24.pdf`** — EBA Filing Rules v5.7 (65pp).
- **`sample_instances.zip`** → `xBRL-CSV.zip` — real EBA sample packages (DPM 4.1,
  "random data … should not be assumed to obey validation rules").
- **`taxo_package.zip`** — EBA taxonomy package **4.1** (Dictionary + Reporting
  Frameworks + Severity).

> ⚠️ **Two gaps to know before building.**
> 1. The taxonomy package and samples are **DPM 4.1**, but our ingested snapshot
>    is **4.2**. Only structural conventions are taken from them (those are
>    stable across releases); version-specific strings (URLs) use 4.2.
> 2. The provided package contains only the "reporting innovations" frameworks
>    (MICA, ESG, PAY, PILLAR3) — **no COREP entry point at all**, and no COREP
>    LCR sample. So the LCR entry-point URL is **derived by the documented
>    pattern and validated against the pillar3/mica samples** (see §5), not read
>    directly. Verify it against the real COREP taxonomy package when available.

The v1 demo module is **COREP LCR** = DPM module `COREP_LCR_DA` (framework COREP,
module version 3.3.0, at release 5 / 4.2), templates C_72–C_77.

---

## 1. Package = a zip conforming to Report Package 1.0 (xbrl.org)

The root folder inside the zip is named **exactly like the zip** (without
`.zip`). Layout:

```
{ReportName}/
├── META-INF/
│   └── reportPackage.json          # fixed content (documentType report-package/2023)
└── reports/
    ├── report.json                 # documentType xbrl-csv 2021; "extends" -> entry point URL
    ├── parameters.csv              # name,value pairs
    ├── FilingIndicators.csv        # templateID,reported
    └── {table}.csv                 # one per reported template; datapoint,factValue[,dims]
```

`META-INF/reportPackage.json` fixed content:
```json
{"documentInfo": {"documentType": "https://xbrl.org/report-package/2023"}}
```

`reports/report.json`:
```json
{"documentInfo": {"documentType": "https://xbrl.org/2021/xbrl-csv",
                  "extends": ["<full absolute entry-point URL>"]}}
```
The `extends` list must have **exactly one** value: the published full JSON
entry-point URL (absolute).

---

## 2. File naming (Filing Rules §"File naming structure for remittance to the EBA")

```
ReportSubject_Country_FrameworkCodeModuleVersion_Module_ReferenceDate_CreationTimestamp.zip
```
(≥ v5.4 the 3rd segment is the **module** version, not the taxonomy version.)

| Segment | Rule | LCR demo value |
|---|---|---|
| `ReportSubject` | LEI + scope suffix for modules without `_con/_ind` in the name: `.IND` (individual), `.CON` (highest consolidated), `.CRDLIQSUBGRP` (liquidity subgroup). | `<LEI>.CON` |
| `Country` | ISO 2-letter country code | e.g. `DE` |
| `FrameworkCodeModuleVersion` | `Framework.Code` (upper) + module version as **6 digits** `XXYYZZ` from `ModuleVersion.VersionNumber` | `COREP030300` (COREP + 3.3.0) |
| `Module` | `ModuleVersion.Code` **without underscores, upper-case** | `COREPLCRDA` |
| `ReferenceDate` | `YYYY-MM-DD` | `2025-12-31` |
| `CreationTimestamp` | `YYYYMMDDhhmmssfff` (17 digits, ms) | run-supplied |

Real example from the rules: `7LTWFZYICNSX8D621K86.CON_DE_COREP040000_COREPOF_2025-12-31_20250327095525486.zip`

**Determinism:** the creation timestamp must be a run **input** (not `now()`),
otherwise the same inputs would not produce a byte-identical package.

---

## 3. parameters.csv

Header is fixed: `name,value`. Rows (order not mandated — we fix a canonical
order for determinism):

| name | value format | when present |
|---|---|---|
| `entityID` | `rs:{LEI}.{scope}` (e.g. `rs:DUMMYLEI123456789012.CON`) | always |
| `refPeriod` | `YYYY-MM-DD` | always |
| `baseCurrency` | `iso4217:{CUR}` (e.g. `iso4217:EUR`) | only if a fact refers to base currency (i.e. any monetary fact) |
| `decimalsMonetary` | integer (e.g. `-3`) | only if a monetary fact present |
| `decimalsPercentage` | integer (e.g. `4`) | only if a percentage fact present |
| `decimalsInteger` | integer (e.g. `0`) | only if an integer fact present |
| `decimalsDecimal` | integer (e.g. `2`) | only if a decimal fact present |

Rule: *don't include* a `baseCurrency`/`decimals*` param if no fact uses it. So
which params appear depends on the **datatypes of the reported datapoints** —
which we know from the taxonomy resolver (datatype code per datapoint).

> Facts-stage `IndicatorsParams` currently carries a single `decimals` int. We
> use it for `decimalsMonetary` and standard defaults for the other present
> types (percentage 4, integer 0, decimal 2). Per-type decimals from the params
> file is a clean refinement for when a real vendor sample pins the layout.

---

## 4. FilingIndicators.csv and {table}.csv

**FilingIndicators.csv** — header `templateID,reported`; one row per template.
`templateID` is the **DB-form** template code (e.g. `K_00.04`), `reported` is
`true`/`false`.

**{table}.csv** — filename is the **lowercase** template code + `.csv`
(`K_00.04` → `k_00.04.csv`; our `C_73.00.a` → `c_73.00.a.csv`). Header is fixed:
`datapoint,factValue` **plus** any open/typed dimension columns the table has.

- **datapoint** = `dp{VariableID}` — literally `dp` + the DPM
  `VariableVersion.VariableID` (NOT the `VariableVID`; those are different id
  spaces). The `VariableID` matches the xBRL taxonomy's datapoint property-group
  keys (verified against the 4.2 `tab/*.json` — `dp146617` etc.); `VariableVID`
  does not and Arelle rejects it as `xbrlce:unknownPropertyGroup`. This is what
  our taxonomy `resolve(template,row,col)` returns as `datapoint_id`, so a fact
  `(template,row,col,value)` becomes `dp{datapoint_id},{value}` in
  `{template}.csv` — the join that ties facts → taxonomy → generation.
- **factValue** = the raw value.
- **Open/typed dimensions** (extra columns like `qEEA`, `PDT`, `ECA`) appear for
  open/dynamic tables. Our demo uses the `.a` "Total currencies" (closed)
  tables → only `datapoint,factValue`. **Open-table keying is v2** per CLAUDE.md;
  v1 handles closed tables and must reject/flag facts needing open dimensions.

---

## 5. Entry-point URL — derived and validated

Pattern (from the sample `report.json` `extends` values):
```
http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/{framework.lower()}/{taxo_version}/mod/{module_code.lower()}.json
```
**Validated** by reconstructing samples from DPM data:

| DPM module (code, version, framework) | Sample filename segment | Sample entry point |
|---|---|---|
| `IRRBBDIS`, 1.0.0, PILLAR3 | `PILLAR3010000_IRRBBDIS` | `.../pillar3/4.1/mod/irrbbdis.json` |
| `CODIS`, 2.0.0, PILLAR3 | `PILLAR3020000_CODIS` | `.../pillar3/4.1/mod/codis.json` |

Both reproduce exactly. Applying it to LCR at 4.2:
```
http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/corep/4.2/mod/corep_lcr_da.json
```
**Confirmed** against the 4.2 taxonomy package (`taxo_package_4.2_hotfix.zip`),
which contains `…/corep/4.2/mod/corep_lcr_da.json` exactly — our generated
package's entry point resolves and Arelle loads it.

---

## 6. Byte format (for deterministic output)

- **CSV**: `CRLF` line endings, incl. a **trailing CRLF** after the last row;
  UTF-8, no BOM. OIM quoting: if a value contains comma / CR / LF / `"`, wrap in
  double quotes and double any inner `"`.
- **JSON**: pretty-printed; line endings don't affect validity.
- The samples use CRLF throughout; `reportPackage.json` is a fixed literal.

**Determinism (CLAUDE.md):** same inputs + same snapshot ⇒ byte-identical zip.
So: fix zip entry timestamps to a constant; insert entries in a fixed sorted
order; sort each `{table}.csv` by datapoint id; canonical parameters order;
creation timestamp is an input. "Byte-identical" means run-to-run stable — not
identical to EBA's sample whitespace.

---

## 7. What generation needs (all injected — generation imports only core)

- **facts**: `(template_code, row_code, column_code, value)` list (from facts).
- **resolver** (from taxonomy): `resolve(template,row,col) -> {datapoint_id, datatype_code}`
  — gives the `dp{id}` and the datatype (to decide parameters).
- **package metadata** (assembled by workflows from snapshot + params + run):
  LEI, scope, country, reference date, creation timestamp, framework code,
  module code, module version, taxonomy version, base currency, decimals, and
  the filing indicators (template + reported). Entry-point URL derived from the
  above (overridable).
- **output store** (from facts): a callback to persist the zip as a `RunFile`
  with role `package_output`.

---

## Filing Rules v5.8 (vs v5.7) — changes affecting us

Diffed the change history (`EBA Filing Rules v5.8_2026_02_25.pdf`). Only two
changes touch our package layout / CSV / naming / parameters:

1. **Reporting subject must be uppercase** — "The reporting subject must be
   written in uppercase when it contains alphabetic character." Applies to the
   filename's `ReportSubject` and `parameters.csv` `entityID`. We already store
   LEIs uppercased; generation now also uppercases the subject defensively.
2. **New xBRL-CSV extra rule 6** — "`{table}.csv` must not be included in the CSV
   reporting package if its filing indicator is negative." Generation is
   compliant by construction (a `{table}.csv` is written only for templates that
   have facts, whose derived indicator is positive); validation adds a
   `NEGATIVE_INDICATOR_CSV` check to catch override misuse / external packages.

Nothing else in v5.8 affects package structure, naming, CSV rules, or parameters.
