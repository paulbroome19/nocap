# Product-contract audit — findings

Audit of the **current application** against [`PRODUCT.md`](../PRODUCT.md), the
product behaviour contract. Baseline: `main` at commit `ab3686c` (xBRL-XML,
DPM-source-form, and deployment work all merged).

**This is a findings report only — nothing is fixed here.** Each finding names
the contract clause it contradicts, what the code actually does, exact
`file:line` evidence, a severity, and whether the contradiction is *wrong
behaviour* (the app actively does the wrong thing) or *absent behaviour* (the
contract mandates something the app does not do).

Severity: **Critical** = breaks a core invariant with regulatory / data-integrity
consequence · **High** = clear contradiction affecting correctness or trust ·
**Medium** = UX / vocabulary / partial-freeze · **Low** = cosmetic.

## Summary

| Severity | Count | Findings |
|---|---|---|
| Critical | 6 | A1, A2, B1, C1, C2, E1 |
| High | 7 | A3, A4, B2, C3, C4, C5, D1 |
| Medium | 13 | A5, B3, C6, E2, F1, F3, F4, F5, F6, F7, F11, F12, F13 |
| Low | 6 | A6, B4, F2, F8, F9, F10 |

The **Critical** picture in one line each:

- **A1** A background ingestion failure leaves a `failed` release row + on-disk residue (creation is not transactional end-to-end).
- **A2** A release **cannot** be deleted while runs reference it — the exact inverse of the contract.
- **B1** The entity **name** is never frozen on a run; it is resolved live, so renaming an entity rewrites historical runs.
- **C1** Re-execution silently re-binds to whatever the live entity/release now is — no change detection, no confirmation.
- **C2** Replacing a release artifact silently changes the inputs a later re-execution runs against — no confirmation.
- **E1** Storage paths/keys are derived from the **user's filename**, not a system key — filename is treated as identity.

A structural theme: much of the contract describes *guardrails around live
dependencies and destructive actions* that the app predates. Several findings are
therefore "mandated behaviour absent" rather than "wrong output" — but in a
regulated-submission product, an absent guardrail is itself a contradiction.

---

## A. Taxonomy release

### A1 — Background ingestion failure leaves a failed release + disk residue · Critical · wrong behaviour
- **Clause**: "Creation is transactional… A release record appears in the regulator's list **only on full success**. Any failure at any stage leaves **no release, no residue on disk**."
- **Current behaviour**: `create_release` verifies the three files synchronously (with correct rollback of the synchronous store step), then schedules the slow DPM conversion + rule ingestion as a **background** task. If that background stage fails, `ingest_snapshot` / `finalize_release` set `status = failed`, write an error, and commit — the snapshot row **and the whole snapshot directory** (stored original, any converted sqlite, taxonomy package, rules workbook) remain. Combined with A3, that failed release then shows in the list.
- **Evidence**: `backend/app/taxonomy/service.py:584-600` (rollback only around synchronous store), `:416-435` (`ingest_snapshot` sets `failed`, commits, no cleanup), `:603-635` (`finalize_release` same), `backend/app/taxonomy/router.py:203-215` (202 + schedules `finalize_release_task`).

### A2 — Deletion is blocked when runs reference the release · Critical · wrong behaviour
- **Clause**: "**Deletion is permitted even when runs reference the release.** Historical runs are unaffected (they are frozen)."
- **Current behaviour**: `delete_release` raises `ConflictError` when `run_count > 0` ("This release cannot be deleted — N runs were produced from it"). The guard is wired to the real run count at the composition root, so it is active in production. This is the exact inverse of the clause, and it also makes the "Release deleted → select a release to continue" dependency scenario (C5) structurally unreachable.
- **Evidence**: `backend/app/taxonomy/service.py:648-667`, `backend/app/main.py:114-117`, `backend/app/workflows/service.py:621`, `frontend/src/api/snapshots.ts:121-125`.

### A3 — Non-usable releases appear in the list · High · wrong behaviour
- **Clause**: "The release list contains **usable releases only**. Never 'ingesting', never 'verifying', never 'failed'. If it is listed, it can be used."
- **Current behaviour**: The list endpoints return every snapshot with no status filter; the frontend renders each with a `StatusBadge` that has dedicated styles for `ingesting`, `failed`, and `artifacts_missing`, and even polls while a release is still `ingesting` — proving non-ready rows are shown.
- **Evidence**: `backend/app/taxonomy/service.py:697-707` (`list_snapshots_for_regulator`, no filter), `:680-683`; `backend/app/taxonomy/router.py:94-103`; `frontend/src/pages/RegulatorReleases.tsx:43,104-135`; `frontend/src/components/StatusBadge.tsx:3-15`.

### A4 — Deletion is offered from the list · High · wrong behaviour
- **Clause**: "Deletion. **From the release's own page only — never from the list** — with confirmation."
- **Current behaviour**: The regulator releases **list** renders a per-row Delete button calling `deleteRelease` directly. (The release's own page also has one, which is correct; the violation is the list also having it.)
- **Evidence**: `frontend/src/pages/RegulatorReleases.tsx:50-62,124-133`.

### A5 — No artifact-replacement control on the release page · Medium · absent behaviour
- **Clause**: "Editing. **Opening a release allows an individual artifact to be replaced**… the previous file is removed… derived state is rebuilt."
- **Current behaviour**: The backend supports per-slot replacement (`POST /snapshots/{id}/artifacts/{slot}`) with correct rebuild semantics (rules re-ingest deletes prior rows; taxonomy slot unlinks the old zip), and an `uploadArtifact` client exists — but `ReleaseDetail.tsx` renders slots as read-only cards with no upload/replace control, and `uploadArtifact` is unused. The clause is unmet on the surface it names. (Re-ingest exists, but rebuilds from the stored original — it is not replacement.)
- **Evidence**: `frontend/src/pages/ReleaseDetail.tsx:182-197`; `frontend/src/api/snapshots.ts:143-175` (unused); backend route `backend/app/taxonomy/router.py:143-172`.

### A6 — Duplicate-rejection message names an internal snapshot id · Low · wrong behaviour
- **Clause**: "Taxonomy artifacts may reject an exact duplicate, **naming the release** that already uses it."
- **Current behaviour**: The rejection says `snapshot id={existing.id}` — an internal id and internal term — rather than the release's business label. Detection itself is correct.
- **Evidence**: `backend/app/taxonomy/service.py:370-376`.

---

## B. Run / execution

### B1 — Entity name is resolved live, never frozen on the run · Critical · wrong behaviour
- **Clause**: "Everything is frozen at execution time: **entity values (name, LEI, country, scope)**… None of these are resolved through live references after the fact." / "Renaming an entity… leaves history exactly as it was."
- **Current behaviour**: `Run` freezes `entity_lei`, `entity_scope`, `country` — but there is **no `entity_name` column**. Every surface that shows the name resolves it live via `run.entity_id`: the run cover (`getEntity` on each load), and the stored validation-report header (`_report_identity` does `db.get(Entity, run.entity_id)`). Rename the entity and the historical run's display changes; delete it and the report falls back to the LEI. LEI/country/scope are correctly frozen — only the name leaks. Found independently by three of the audit passes.
- **Evidence**: `backend/app/workflows/models.py:198-219` (no name column); `backend/app/workflows/service.py:883-906` (`_report_identity` live lookup); `backend/app/workflows/schemas.py:137-162` (`RunOut` has no name); `frontend/src/pages/run/RunLayout.tsx:37`, `frontend/src/pages/run/RunCover.tsx:76`.

### B2 — No run-deletion path; code codifies the opposite invariant · High · absent behaviour + brief conflict
- **Clause**: "Deletion. An individual execution can be deleted from its own page, with confirmation. Deletion removes the run and its artifacts."
- **Current behaviour**: There is no `delete_run` service, no `DELETE /runs/{id}` route, and no delete control in the UI. The `Run` model docstring and `CLAUDE.md:202` both assert "Runs are never deleted" — the contradictory invariant, stated as intentional.
- **Evidence**: `backend/app/workflows/models.py:8`; no `db.delete(run)` anywhere in `backend/app/workflows/service.py`; no delete route in `backend/app/workflows/router.py`; `CLAUDE.md:202`.

### B3 — Declarations are not frozen on the run; re-read live at execution · Medium · wrong behaviour
- **Clause**: "A run **freezes the declarations and parameters it used**."
- **Current behaviour**: Parameters *are* frozen (`Run.base_currency`, `Run.decimals` at `create_run`). Declarations are **not** persisted — `_load_declarations` reads the live `EntityWorkflowConfig` during `execute_run`. The run stores only the *derived outcome* (`Run.filing_indicators`), which also flattens Required and Not-required both to `source="declared"`, so the declaration map that produced the run is never captured. A config edit between `create_run` and `execute_run` changes what the run uses.
- **Evidence**: `backend/app/workflows/service.py:778-783` (`_load_declarations` live), called at `:1134`; `Run` model has no declarations column (`models.py:198-261`); contrast params frozen at `:528-544`.

### B4 — Instance identity is unenforced free-text · Low · ambiguous
- **Clause**: Instance = "entity + reporting date + snapshot + adjusted + version, per workflow."
- **Current behaviour**: `snapshot_key` / `adjusted_key` / `version_key` are nullable free-text with no uniqueness constraint ("identity binding arrives with the Audit stage"). Grouping into an instance *does* work today (backend `INSTANCE_IDENTITY`; frontend `instanceSiblings`), so behaviour matches the clause; the missing DB constraint is a robustness gap, not a present contradiction.
- **Evidence**: `backend/app/workflows/models.py:222-225`; `backend/app/workflows/service.py:555-565`; `frontend/src/pages/run/context.ts:30-38`.

---

## C. Dependency changes

The central gap: **no code path detects that an entity or release used by a prior
execution has changed or disappeared and stops for deliberate user action.**

### C1 — Re-execution silently re-binds to live dependencies · Critical · wrong behaviour
- **Clause**: "Live dependencies must be confirmed, never assumed… requires deliberate user action before any new execution." / "The system **never silently substitutes** a dependency."
- **Current behaviour**: `reexecute_run` re-reads the source run's `entity_id` / `snapshot_id` / `release_id` and passes them into `create_run`, which resolves the **live** entity and snapshot and captures their current values — no diff against what the instance previously used, no flag, no confirmation. The frontend `handleResubmit` runs reexecute → attach → execute with no confirmation step.
- **Evidence**: `backend/app/workflows/service.py:568-601`, `:491`, `:477-489`; `frontend/src/pages/run/RunCover.tsx:86-101`.

### C2 — Replaced release artifact changes re-execution inputs with no confirmation · Critical · wrong behaviour
- **Clause**: "Release artifact replaced → **confirm before executing against changed inputs**."
- **Current behaviour**: `store_artifact` replaces an artifact in place under the same `snapshot_id`. A run bound to that snapshot re-executed later reads the replaced artifact via `open_lookup` and re-derives capabilities with zero confirmation; nothing compares the run's stored `capabilities`/binding against the changed release.
- **Evidence**: `backend/app/taxonomy/artifacts.py:370-395`; `backend/app/workflows/service.py:1112-1113`, `:524-527`; no confirm path in `reexecute_run` (`:568-601`) or `RunCover.tsx:86-101`.

### C3 — Frontend silently swallows missing dependencies and still offers re-execute · High · wrong behaviour
- **Clause**: "never silently proceeds against a missing one" / "requires deliberate user action."
- **Current behaviour**: `RunLayout` loads entity and release with `.catch(() => {})`, swallowing a 404 for a deleted entity/release. The cover falls back to `entity_lei` / release `"—"` with no signal, and the Re-execute button stays enabled. Backend errors surface as raw `e.message`.
- **Evidence**: `frontend/src/pages/run/RunLayout.tsx:37-38`; `frontend/src/pages/run/RunCover.tsx:76,220-264,97-100`.

### C4 — "Entity deleted → select a current entity" flow absent; message technical · High · absent behaviour
- **Clause**: "Entity deleted → 'The entity used for this execution no longer exists. Select a current entity to continue.'"
- **Current behaviour**: No entity-deletion path exists, so the scenario can't be reached via supported flows; where `reexecute_run` guards `entity_id is None` it raises the technical "run id={id} has no entity; cannot re-execute" with no reselection flow. A directly-removed entity row would make `get_entity` raise a bare `NotFoundError`.
- **Evidence**: `backend/app/workflows/service.py:580-582`, `:179-183`; `backend/app/workflows/models.py:213-215` (nullable FK, no cascade); no entity-delete route.

### C5 — "Release deleted → select a release" flow absent & unreachable · High · absent behaviour
- **Clause**: "Release deleted → 'This instance previously used release 4.2, which no longer exists. Select a release to continue.'"
- **Current behaviour**: Blocked by A2 (a referenced release cannot be deleted), so the scenario is structurally unreachable and no "select a release" handling exists; a snapshot removed by other means makes `get_snapshot` raise a generic `NotFoundError`.
- **Evidence**: `backend/app/taxonomy/service.py:662-667`; `backend/app/workflows/service.py:710-714`, `:583-596`.

### C6 — Entity value change not recorded as visible in the execution record · Medium · partial
- **Clause**: "Entity values changed → proceed with current values, **but the change is visible in the execution record**."
- **Current behaviour**: "Proceed with current values" holds (re-execution freezes current LEI/scope/country). But the run stores no change flag/diff and no name, so a change is only implicitly reconstructable by comparing two runs' frozen fields — and a name-only change is invisible.
- **Evidence**: `backend/app/workflows/service.py:583-596`; `backend/app/workflows/models.py:212-219`.

---

## D. Entity

### D1 — Entity deletion is not implemented · High · absent behaviour
- **Clause**: "Entities are freely editable and **freely deletable** — this is a live reference table."
- **Current behaviour**: The entity service has create/update/get/list but **no delete**; the router has no `DELETE /entities/{id}`. An analyst cannot delete an entity.
- **Evidence**: `backend/app/workflows/service.py:205,220` (no delete); `backend/app/workflows/router.py:120-154`.

*(The "edits never affect existing runs" clause is violated only by the entity **name** — see B1.)*

---

## E. Storage & identity

### E1 — Storage keys/paths are derived from the user filename · Critical · wrong behaviour
- **Clause**: "Every stored artifact receives a **system-generated storage key, unique per upload, independent of the user's filename**… Nothing keys behaviour, lookup, or paths off a user-supplied name." / Principle: "User-supplied filenames are metadata, never identity."
- **Current behaviour**: `store_run_file` builds the path as `directory / filename` and sets `storage_key = runs/{run_id}/{role}/{user_filename}` — not system-generated, not unique per upload (two uploads of the same filename to the same run+role overwrite each other and re-derive the same key). `ReleaseArtifact` does the same (`target_dir / filename`). The filename *is* the identity/path. (The snapshot's original DPM source is exempt — it uses a fixed system name.)
- **Evidence**: `backend/app/facts/service.py:68-79`, `:106-110`; `backend/app/taxonomy/artifacts.py:377-390`.

### E2 — Reconciliation is one-directional only · Medium · absent behaviour
- **Clause**: "The database and the filesystem must agree. Reconciliation detects and reports **records without files and files without records**."
- **Current behaviour**: Reconciliation exists only for snapshots and only records→files (`verify_snapshot` flips `ready` ↔ `artifacts_missing`). Nothing scans the filesystem for orphaned files with no DB record; `RunFile` bytes are checked one-at-a-time on read but never swept in either direction.
- **Evidence**: `backend/app/taxonomy/service.py:727-763`; `backend/app/main.py:74-94`.

---

## F. Interaction rules (frontend)

**States**
- **F1 · Medium** — `SuitePage` shows the definitive "No ready taxonomy releases…" message while the fetch is in flight and permanently on failure (no loading flag, no `.catch`). `frontend/src/pages/SuitePage.tsx:60-65,164-167`.
- **F2 · Low** — List screens render an empty white card instead of an empty state; some swallow the regulator-lookup error. `Reporting.tsx:23-36`, `RegulatorReporting.tsx:14-16,31-43`, `Regulators.tsx:23-36`, `SettingsReporting.tsx:24-37`.

**Confirmation**
- **F3 · Medium** — Release deletion uses a bare `window.confirm("Delete {name}? This cannot be undone.")` — browser chrome, not a styled dialog, and does not enumerate what deletion removes. `RegulatorReleases.tsx:51`, `ReleaseDetail.tsx:84`.

**Unsaved changes**
- **F4 · Medium** — No unsaved-changes guard anywhere (no `beforeunload`/`useBlocker`/dirty tracking). Changing the entity/suite selector in `FilingIndicators`/`Parameters` silently overwrites in-progress edits. `FilingIndicators.tsx:34-52`, `Parameters.tsx:29-43`, `EntityForm.tsx:97-101`.

**Vocabulary** (contract: "Statuses read in business language… never internal enum values")
- **F5 · Medium** — `StatusBadge` renders raw snapshot enum values (`ingesting`/`ready`/`failed`/`artifacts_missing`). `StatusBadge.tsx:10-15,25`.
- **F6 · Medium** — Release slot status renders raw enum (`empty`/`uploaded`/`verifying`/`ready`/`failed`). `ReleaseDetail.tsx:27-37`.
- **F7 · Medium** — Filing-indicator "Filed" column prints `true`/`false` instead of Filed / Not filed. `run/RunIndicators.tsx:56`.
- **F8 · Low** — Validation register chips print `PASSED`/`FAILED`/`WARNING`/`NOTE`/`DEACTIVATED` and a lowercase "severity unknown". `run/RunValidation.tsx:160,96-97`.
- **F9 · Low** — Package file role falls back to the raw role token (`package_output`); lowercase "unavailable". `run/RunPackage.tsx:101,119`.
- **F10 · Low** — One gesture, three verbs: heading "Re-execute / Resubmit", opener "Re-execute", confirm "Resubmit". `run/RunCover.tsx:213,224-227,247`.

**Errors / identifier exposure** (contract: "Never expose internal identifiers… file paths"; audience has no terminal or repo)
- **F11 · Medium** — Internal requirement code "FR 1.12" rendered in the Re-execute card. `run/RunCover.tsx:216`.
- **F12 · Medium** — The wizard's "Convert it first" disclosure tells the analyst to run `python -m app.taxonomy.convert …` from "the project's `backend` folder" and points at `docs/deployment.md` — repo paths + developer commands in the reporting UI. `frontend/src/pages/ReleaseWizard.tsx:152-165`.
- **F13 · Medium** — Backend error strings are rendered verbatim (`parseError` → `ErrorText`/banners/`release.error`/`slot.error`); backend messages contain internal vocabulary and ids (e.g. "snapshot id=X not found", "snapshot artifacts are missing on disk"), so internal terms/ids reach the analyst unfiltered. `snapshots.ts:82-89`, `workflows.ts:202-209`, `ReleaseDetail.tsx:157,193`.

*Ambiguous (frontend-only inspection):* `run/RunValidation.tsx:86` renders `{row.id}` as a mono chip — legitimate if it is the regulator's rule code (FR refs / formula ids), a contradiction if an internal `NC-S**`/register id; the register mixes both, so some rows show internal codes. `ErrorPage.tsx:16-21` renders a thrown error's `message` on the non-404 branch (low practical exposure).

---

## Contract ↔ engineering-brief conflicts (CLAUDE.md)

Two long-standing CLAUDE.md statements now contradict the adopted contract and
should be reconciled (CLAUDE.md wins on structure, PRODUCT.md on behaviour):

- **CLAUDE.md core principle 2**: "**Snapshots are sealed.** Once a DPM release is ingested it is **never modified**." vs PRODUCT.md's release **Editing** clause (an artifact may be replaced and derived state rebuilt). The artifact-slot work already makes releases editable in the backend.
- **CLAUDE.md Workflow UX ("Runs are never deleted", line 202)** and the `Run` model docstring vs PRODUCT.md's run **Deletion** clause (B2).

These are documentation conflicts, not code findings, but they explain B2/A5 and
should be settled when those are addressed.

---

## Behaviours the contract does not yet cover (gaps to decide, not contradictions)

Surfaced by the audit but out of scope of the current contract text — worth a
contract decision rather than an implementation guess:

- **Output format** (xBRL-CSV vs xBRL-XML per regulator/module) — shipped in the backend with API but no contract clause on how a user chooses or sees it (relates to backlog #37).
- **Validation & findings** — the contract says validation *results* are frozen (satisfied) but is silent on the findings/register presentation, severities, and formula-availability messaging (F8 sits in this gap).
- **Comparison** and **Sign-off / sealed submissions** — future objects (backlog #32, #33); the contract references sign-off only as a "future constraint."

---

## Clauses verified compliant (reported for balance)

- Filing-indicator **outcomes** and **parameters** are frozen on the run; re-execution is append-only and does not mutate history; failed executions remain visible. (Run slice.)
- Declaration **state semantics** (Required / Optional / Not required, incl. the exclusion warning naming template + count) are implemented correctly. (Config slice.)
- Fact files can be re-uploaded across entities/dates/re-executions with no duplicate error (no unique checksum constraint on `RunFile`); taxonomy exact-duplicate rejection exists. (Storage slice.)
- Navigation: a styled in-shell 404 and a root error boundary are wired; legacy deep links redirect. Progress for long operations is shown where started and survives navigation. Dates render `DD MMM YYYY` consistently. (Interaction slice.)
- Release **deletion completeness** — when it is allowed to run, it removes rules, artifact rows, the snapshot row, and the whole snapshot dir (no residue). (Its problem is being *blocked* — A2.)

---

## Method

Audited by five parallel read-only passes, one per contract slice (release
lifecycle, run freezing, dependency-change guards, entity/config/storage,
frontend interaction rules), each required to cite `file:line` evidence and to
report only genuine contradictions grounded in code actually read. Findings were
then deduplicated across passes (e.g. the entity-name leak B1 surfaced in three
passes; the deletion-blocked A2 in two). No fixes were made.
