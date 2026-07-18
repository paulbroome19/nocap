# NoCap — EBA xBRL-CSV Submission Platform

## What this is

A production-minded web application that replaces an external vendor for EBA regulatory
submissions. It ingests EBA DPM taxonomy releases, accepts fact data as XLSX
(report / row / column / value), and generates submission-ready xBRL-CSV packages (zip)
plus a validation report.

v1 target: COREP LCR, end to end. FINREP is a fast-follow. The architecture must never
assume a single reporting suite.

## Core principles (do not violate)

1. **Taxonomies are data, not code.** EBA DPM releases are uploaded through the app and
   stored as immutable, versioned snapshots. There are NO per-taxonomy or per-suite
   folders in the repo. New releases = new database rows, zero code changes.
2. **Snapshots are sealed.** Once a DPM release is ingested it is never modified.
   New releases sit alongside old ones. Every run records exactly which snapshot it used.
3. **Runs are reproducible.** A run persists its inputs (files as uploaded, byte-for-byte),
   its snapshot reference, its parameters, and its outputs. Any historical run can be
   inspected and its output re-derived.
4. **Facts are append-only.** Reported values are events (value, datapoint, entity,
   reference date, run, timestamp). Never update in place. Current state is a view.
5. **Stages do not import each other.** Only `workflows/` orchestrates. See dependency
   rules below.
6. **Suites are configuration.** "COREP LCR" and "FINREP" are workflow configuration
   records pointing at modules within a snapshot — not code branches. Genuinely
   suite-specific logic, if ever needed, is an explicitly marked exception in `generation/`.

## Repo structure

```
nocap/
├── backend/
│   ├── app/
│   │   ├── core/            # config, db session, logging, errors — NO business logic
│   │   ├── taxonomy/        # DPM release upload, snapshot registry, datapoint lookup
│   │   ├── facts/           # XLSX ingestion + filing indicators + parameters files
│   │   ├── generation/      # facts + snapshot -> xBRL-CSV package (zip)
│   │   ├── validation/      # structural checks v1; Arelle adapter slots in here v2
│   │   ├── comparison/      # v2 scaffold only: our zip vs vendor zip regression diff
│   │   └── workflows/       # orchestration: workflow configs, Run lifecycle
│   ├── tests/               # mirrors app/ package-for-package
│   ├── alembic/             # migrations from the very first table
│   └── pyproject.toml
├── frontend/
└── docs/
```

Each stage package (`taxonomy`, `facts`, `generation`, `validation`, `comparison`)
contains its own `models.py`, `service.py`, `router.py`, `schemas.py`. Identical layout
in every stage.

### Dependency rules (enforce strictly)

- `core` imports nothing from `app/` — it is the bottom layer.
- Stage packages may import from `core` only. A stage NEVER imports another stage.
- `workflows` may import from any stage. It is the only package that knows the pipeline
  sequence.
- Routers are thin: parse request, call service, shape response. All logic lives in
  services as plain Python that does not know HTTP exists.

## Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, Postgres.
  Python is non-negotiable: the v2 validation layer wraps Arelle (open-source XBRL
  processor, Python) in-process.
- **Frontend:** React + Vite, TypeScript, Tailwind. Clean, minimal, professional.
  This will be demoed to bank management — it must look credible, not like a hackathon.
- **Hosting:** Railway (web service + Postgres). Twelve-factor config via env vars only.
  No secrets in the repo. The app must not care where it runs.

## Domain model (v1)

- `TaxonomySnapshot` — one row per uploaded DPM release: version label, uploaded_at,
  checksum, status (ingesting/ready/failed). DPM content stored keyed by snapshot id.
  The EBA publishes DPM 2.0 as a SQLite database — ingestion reads that file.
- `WorkflowConfig` — a reporting suite workflow: name (e.g. "COREP LCR"), module
  reference within a snapshot, active flag.
- `Run` — one execution: workflow, snapshot id, reference date, entity identifier,
  status, created_at, created_by (nullable in v1, real in v2 when auth lands).
- `RunFile` — every file attached to a run, inputs and outputs, stored as uploaded:
  role (fact_input / indicators_params / package_output / validation_report), filename,
  bytes or object-store key, checksum.
- `Fact` — append-only: run id, datapoint/template-row-column reference, value,
  entity, reference date.

## Input contracts

The **fact file is the only required input**. Filing indicators and package
parameters are **derived in-system** by default (see below); an uploaded
indicators/parameters file is an optional "advanced" override.

1. **Fact file (XLSX):** columns are report, row, column, value — confirmed sample:
   `C_67_00, 0010, 0010, 100000`. Three template-code forms exist and are all
   accepted: upstream `C_67_00`, DPM/DB `C_67.00`, EBA display `C 67.00`. The
   canonical stored form is the **DB form `C_67.00`** (the space form appears
   nowhere in the DPM 2.0 database). Row/column are 4-digit EBA codes — preserve
   leading zeros (never let them become integers). Open/dynamic tables (DPM marks
   them with a `KeyID` on the table version) are **not generated in v1**: a fact
   targeting one yields a clear `OPEN_TABLE_UNSUPPORTED` validation error rather
   than a malformed CSV. Proper open-table keying is a v2 concern.
2. **Derived indicators & parameters (default):** the run derives these from the
   fact data + the selected entity, so no second file is needed:
   - *Filing indicators*: every module template, reported iff it has (resolvable,
     closed-table) facts.
   - *Parameters*: `entityID` from the entity's LEI + scope, `refPeriod` from the
     run's reference date, `baseCurrency` from a run setting (default EUR),
     `decimals` from a run field (default -3).
3. **Indicators & parameters file (optional override):** filing indicators plus
   package parameters (entity LEI, reference date, base currency, decimals). The
   parser lives behind an interface so the layout can shift without touching
   generation; when uploaded it replaces the derived values. Validation checks
   the derived outputs exactly as it checks uploaded ones.

Entities are selected from a lookup (name, LEI, country, default scope); the run
captures the entity's LEI/country/scope at creation for reproducibility.

Parse defensively: trim whitespace, tolerate numeric-vs-text cells for codes, reject
with precise row-level error messages (file, sheet, row number, what was wrong).
Input rejection messages are a feature, not an afterthought.

## Output contract

A zip conforming to the xBRL-CSV (OIM) EBA filing rules:
- one CSV per reported template, named per EBA conventions
- `report.json` / metadata JSON referencing the correct taxonomy entry point
- `parameters.csv` and filing indicators per EBA filing rules
- deterministic output: same inputs + same snapshot = byte-identical zip
  (fix timestamps inside the zip; sort rows deterministically)

Validate the exact naming/layout against the EBA filing rules document for the taxonomy
release in use — do not guess from memory.

## Validation (v1 scope)

Structural report only, rendered in the UI and downloadable:
- every (report, row, column) in the input resolves to a datapoint in the bound snapshot
- values parse under the datapoint's datatype
- filing indicators consistent with templates actually populated
- parameters complete and well-formed
- package layout conforms to spec

Design the report model as generic findings (severity, code, message, location) so the
v2 Arelle-based EBA formula validation emits into the same structure. Do NOT attempt
EBA formula rules in v1.

## Workflow UX (v1)

1. Admin page: upload DPM release -> snapshot appears in registry with status.
2. Workflow list: shows configured suites (v1: COREP LCR).
3. Run screen: select snapshot, reference date, entity; upload fact XLSX; upload
   indicators/params file; press Run.
4. Run detail: status, validation findings table, download package zip, download
   validation report, full input file list. Runs are never deleted.
5. Run history per workflow.

## v2+ (scaffold seams now, do not build)

- `auth/` package: accounts, sessions, roles. Sign-off (maker-checker) lives in
  `workflows/` as run state: a run requires approval by a user other than its creator
  before the package is marked releasable.
- `comparison/`: upload two zips (ours vs vendor), produce a fact-level diff report.
  This is the vendor-replacement evidence engine and future regression suite.
- `validation/`: Arelle adapter executing the EBA formula ruleset (minus the EBA
  deactivated-rules list) against candidate packages.
- Taxonomy diff view between snapshots.

## Engineering conventions

- Alembic migration for every schema change, from the first table onwards.
- Tests mirror `app/` structure; every stage service gets tests against fixture files.
  Keep small fixture XLSX + DPM extracts in `tests/fixtures/`.
- Type hints everywhere; pydantic schemas at all boundaries.
- Structured logging with run id on every log line once a run starts.
- No real bank data, ever, in this environment. All demo values are fictional.
