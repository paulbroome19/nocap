# DPM 2.0 database — exploration notes

Reference material for the taxonomy, facts, generation, and validation stages.
Derived from the real EBA release placed in `docs/reference/` (untracked):

- **File:** `DPM2 Database_v 4_2_20251125.zip` → `DPM2 Database_v 4_2_20251125.accdb`
- **Release:** DPM 2.0, framework version **4.2**, dated 2025-11-25.

> ⚠️ **Format finding — read this first.** The EBA publishes the DPM 2.0
> database as a **Microsoft Access `.accdb`** (755 MB uncompressed), **not
> SQLite** as `CLAUDE.md` assumes. There is no SQLite file in the release. This
> affects the ingestion design (see "Implications for ingestion" at the bottom).
> These notes were produced by converting the relevant tables to SQLite with
> `mdbtools` (`mdb-schema` / `mdb-export -I sqlite`) and querying with `sqlite3`.

Access stores booleans as `-1` (true) / `0` (false).

---

## 1. The database holds *many* releases, not one

A single `.accdb` contains the full release history. The `Release` table:

| ReleaseID | Code | Date | IsCurrent | Status |
|---|---|---|---|---|
| 1 | 3.4 | 2024-02-06 | 0 | released |
| 2 | 3.5 | 2024-07-11 | 0 | released |
| 3 | 4.0 | 2024-12-19 | 0 | released |
| 4 | 4.1 | 2025-04-28 | 0 | released |
| 5 | 4.2 | 2025-10-31 | -1 | validation |

Almost every content table is **release-versioned** via `StartReleaseID` /
`EndReleaseID`. The end is **exclusive**: a row is valid for release `R` iff

```
StartReleaseID <= R AND (EndReleaseID IS NULL OR EndReleaseID > R)
```

So a **snapshot** (in our domain model = one uploaded DPM release) is really
*(this file, a chosen ReleaseID)*. For v1 bind to the current release
(`Release.IsCurrent = -1`, here 4.2 / ReleaseID 5) unless a specific release is
requested. Every lookup must carry the release id and apply the predicate above,
or joins fan out across historical versions (a real duplicate-row bug — see §5).

---

## 2. Keying: framework → module → template → row/col/sheet → datapoint

```
Framework (COREP, FINREP, …)
  └─ Module ── ModuleVersion (Code e.g. COREP_LCR_DA, release-versioned)
        └─ ModuleVersionComposition ── TableVersion   (the templates in the module)
              └─ TableVersion.Code  = template code  (e.g. "C_67.00.a")
                    └─ Cell (TableID, RowID, ColumnID, SheetID)   the grid
                          └─ TableVersionCell (TableVID, CellID)
                                └─ VariableVID  = the DATAPOINT
                                      └─ VariableVersion → Property → DataType
```

### Frameworks / modules
- `Framework` — `Code`, `Name`. COREP = FrameworkID 2, FINREP = 1. (20 frameworks
  incl. DORA, MICA, IRRBB, …)
- `Module` → `Framework`. `ModuleVersion` carries the human code + release window.
- **COREP LCR is the `COREP_LCR_DA` module** ("LCR Delegated Act - COREP"),
  current `ModuleVID = 500`. Its templates are **C_72–C_77** (+ `C_00.01` Nature
  of Report). List a module's templates via `ModuleVersionComposition`.

### Templates (= "table versions")
- A `Table` is the abstract grid; a `TableVersion` (`TableVID`) is its
  release-specific incarnation. **`TableVersion.Code` is the template code.**
- **Codes are stored as `C_67.00` — underscore after the letter, dot before the
  two-digit suffix.** Confirmed: **zero** codes in the whole DB contain a space.
  Variant suffixes exist: `C_67.00.a` (Total currencies), `C_67.00.w`
  (Significant currencies, open by currency), `.b`, `.y`, etc.

### Rows / columns / sheets (`Header`)
- `Header.Direction`: **`X` = columns, `Y` = rows, `Z` = sheets** (the open/third
  dimension, e.g. per-currency). Counts: X 8 950, Y 14 044, Z 543.
- **`HeaderVersion.Code` holds the 4-digit ordinate code** (`0010`, `0020`, …),
  stored as text — **leading zeros are significant and preserved**. Row/column
  codes are per-`TableID` and release-versioned.

### Cells and datapoints
- `Cell` (per `TableID`): `RowID` → the Y `HeaderID`, `ColumnID` → the X
  `HeaderID`, `SheetID` → the Z `HeaderID`. (Confirmed by joining
  `Cell.RowID/ColumnID = HeaderVersion.HeaderID`.)
- `TableVersionCell` (`TableVID`, `CellID`) → **`VariableVID` (the datapoint)** and
  a human-readable `CellCode` signature, e.g. `{C_67.00.a, r0020, c0060, s0010}`.
- `Variable.Type` ∈ {**`fact`** (145 176), **`filingindicator`** (654), **`key`**
  (300)}. Fact datapoints are what `(template,row,col)` resolves to. Filing
  indicators are Variables whose `VariableVersion.Code` **is the template code**
  (e.g. `B_01.01`) — one per reported template (pointer for the facts stage).

### Datatype
- `VariableVersion.PropertyID` → `Property.DataTypeID` → `DataType`. `Property`
  also carries `IsMetric`, `PeriodType` (e.g. `Stock`/`Flow`), `ValueLength`.
- **`DataType` (13 rows)** — code → name:
  `i` integer · `r` decimal · `s` string(non-empty) · `b` boolean · `t` true ·
  `dt` date-time · `d` date · `e` enumeration · `m` **monetary** · `p` percentage ·
  `u` URI · `o` ordinals · `es` string(incl. empty).
- Fact-datapoint datatype spread (current release): monetary 97 875, percentage
  7 977, integer 6 291, enumeration 2 277, decimal 1 216, string 895, boolean 247,
  date 130, … — **monetary dominates**; validation must handle all of these.

---

## 3. Canonical resolution query (template, row, col) → datapoint + datatype

For a chosen release `:R` (bind current = 5), and a specific `TableVID`:

```sql
SELECT tv.Code AS template, ry.Code AS row_code, cx.Code AS col_code,
       tvc.VariableVID AS datapoint, dt.Code AS datatype, dt.Name AS datatype_name,
       tvc.CellCode
FROM TableVersion tv
JOIN Cell c            ON c.TableID = tv.TableID
JOIN HeaderVersion ry  ON ry.HeaderID = c.RowID    AND ry.Code = :row
                          AND ry.StartReleaseID <= :R AND (ry.EndReleaseID IS NULL OR ry.EndReleaseID > :R)
JOIN HeaderVersion cx  ON cx.HeaderID = c.ColumnID AND cx.Code = :col
                          AND cx.StartReleaseID <= :R AND (cx.EndReleaseID IS NULL OR cx.EndReleaseID > :R)
JOIN TableVersionCell tvc ON tvc.TableVID = tv.TableVID AND tvc.CellID = c.CellID
JOIN VariableVersion vv   ON vv.VariableVID = tvc.VariableVID
                          AND vv.StartReleaseID <= :R AND (vv.EndReleaseID IS NULL OR vv.EndReleaseID > :R)
JOIN Property p           ON p.PropertyID = vv.PropertyID
JOIN DataType dt          ON dt.DataTypeID = p.DataTypeID
WHERE tv.Code = :template
  AND tv.StartReleaseID <= :R AND (tv.EndReleaseID IS NULL OR tv.EndReleaseID > :R);
```

Worked example (release 5): `C_67.00.a`, row `0020`, col `0060` → datapoint
`VariableVID 5426985`, datatype `m` (monetary), `PeriodType = Stock`,
`CellCode {C_67.00.a, r0020, c0060, s0010}` — exactly one row with the
exclusive-end predicate applied (without it, historical HeaderVersions fan the
result out to 6 duplicate rows).

Open/`Z` tables: a `(template,row,col)` may map to multiple cells across sheets
(`SheetID`). For `.a` "Total currencies" the sheet is a single `s0010`. Proper
open-table (per-currency) keying is a **v2** concern; v1 carries the upstream
placeholder identifier (e.g. row `9990`) through as-is per `CLAUDE.md`.

---

## 4. Template-code normalisation — THREE forms, not two

`CLAUDE.md` assumes two forms (`C_67_00` ↔ `C 67.00`). The real DB adds a third:

| Form | Example | Where |
|---|---|---|
| Upstream fact file | `C_67_00` | separators are all underscores |
| **DPM 2.0 DB (this file)** | `C_67.00` | **underscore after letters, dot before suffix** |
| EBA filing / xBRL "display" | `C 67.00` | space after letters, dot before suffix |

The space form (`C 67.00`) **does not appear anywhere in the DB**. So the lookup
service must normalise an incoming code to the **DB form `C_67.00`** to query,
independent of whatever canonical form we store on facts. Parse into
`(letters, major, minor, optional suffix)` and re-render:

- DB / query form: `C` + `_` + `67` + `.` + `00` + suffix → `C_67.00.a`
- EBA display form: `C` + ` ` + `67` + `.` + `00` + suffix → `C 67.00.a`

Accept all three on input; treat letters case-insensitively; preserve any
lowercase variant suffix (`.a`, `.w`, …). (The xBRL-CSV file-naming form is the
generation stage's concern and must be validated against the EBA filing-rules
doc for 4.2 — do not assume it here.)

Row/column codes: always **text**, zero-padded to 4 digits, never integers.

---

## 5. Gotchas
- **Access, not SQLite** (see top).
- **Release fan-out**: forgetting the exclusive-end predicate silently multiplies
  rows across historical versions. Every join to a `*Version`/`HeaderVersion`
  table needs it.
- **Multiple releases in one file**: "which release" is a required lookup param.
- **Booleans are `-1`/`0`** (Access).
- **`Table` is a reserved-ish name**; quote identifiers.
- Duplicate `TableVersion.Code` across `TableID`s and releases — always qualify by
  release, and by module when resolving within a workflow.

## 6. Implications for ingestion (for Step 2 discussion)
Because the source is Access, "v1 queries the SQLite file directly per snapshot"
(CLAUDE.md) can't be taken literally. Recommended: **on ingest, convert the
`.accdb` to a per-snapshot SQLite file** (via `mdbtools`) stored under the
snapshot's data dir, then all lookups query that SQLite — preserving the
"taxonomies are sealed data, queried per snapshot" principle while matching the
real EBA format. Alternative (query Access directly) is far less portable and
fights the Arelle/Python v2 direction. Flagging for sign-off before building.

### Key tables actually needed for the lookup contract
`Framework, Module, ModuleVersion, ModuleVersionComposition, Table,
TableVersion, TableVersionHeader, Header, HeaderVersion, Cell,
TableVersionCell, Variable, VariableVersion, Property, DataType, Release`
(+ `Context`/`ContextComposition`/`Item`/`Category` for dimensional context, v2).
