# NoCap — Product Contract

This document defines how the system must **behave**. CLAUDE.md defines how it is
**built**. Where they disagree, this document wins on behaviour and CLAUDE.md wins
on structure.

Every PR touching a user-facing surface is reviewed against this document. Any
behaviour not covered here is a gap in the contract — raise it and get it decided
rather than inventing an answer in code.

---

## Who this is for

A regulatory reporting analyst at a bank. They understand COREP, FINREP, filing
indicators, and reference dates. They do not have a terminal, a code repository,
or an engineer sitting next to them. They care about being correct, being able to
prove they were correct, and not being surprised.

They are risk-averse and their institution is reputationally exposed. Ambiguity is
a defect.

---

## Core principles

1. **Airtight over flexible.** No partial states a user can wander into. An object
   either exists and is complete, or it does not exist.
2. **Every execution is frozen.** A run captures the values it used — it never
   resolves them later.
3. **Live dependencies must be confirmed, never assumed.** Entities and taxonomy
   releases can change or be deleted; the system flags this and requires deliberate
   user action before any new execution.
4. **Business vocabulary on every surface.** Technical identifiers are evidence,
   not interface.
5. **Accept inputs as the source publishes them.** Unwrapping, extraction, and
   conversion are the system's job, never the user's.
6. **User-supplied filenames are metadata, never identity.**
7. **Every error names the problem and the next action.**
8. **Nothing is destroyed silently, and nothing is retained secretly.** Deletion
   removes everything it claims to; audit trails record everything they claim to.

---

## Objects

### Taxonomy release

A release is one regulator's framework publication (e.g. EBA 4.2), consisting of
three functional artifacts: the validation rules workbook, the DPM database, and
the taxonomy package.

**Creation is transactional.** The wizard performs upload → verification →
conversion → rule ingestion, showing progress in the wizard itself. A release
record appears in the regulator's list **only on full success**. Any failure at
any stage leaves no release, no residue on disk, and a plain-language explanation
of what went wrong and what to do.

**The release list contains usable releases only.** Never "ingesting", never
"verifying", never "failed". If it is listed, it can be used.

**Naming follows the regulator's own page.** Each slot names the file as the
publisher names it, identifies the section it appears under, and warns about the
confusable neighbour (DPM 1.0 vs 2.0; "Full taxonomy" vs "Taxonomy package").
Item names are matched by prefix — publishers rename between releases.

**Editing.** Opening a release allows an individual artifact to be replaced. The
replacement is verified, the previous file is removed from storage, and any
derived state (converted database, ingested rules) is rebuilt.
*Future constraint:* once sign-off exists, a release referenced by a sealed run
becomes immutable.

**Deletion.** From the release's own page only — never from the list — with
confirmation. Deletion removes every trace: database records, converted database,
stored originals, taxonomy package, ingested validation rules, and any derived
artifacts on disk. After deletion the same files can be uploaded again cleanly.

**Deletion is permitted even when runs reference the release.** Historical runs
are unaffected (they are frozen). New executions against a deleted release must
flag it — see *Dependency changes*.

### Entity

A reporting entity: name, LEI, country, consolidation scope.

Entities are freely editable and freely deletable — this is a live reference table.

**Edits never affect existing runs.** A run holds the entity values it used.
Renaming an entity, correcting an LEI, or deleting the entity entirely leaves
history exactly as it was.

**A re-execution uses current values**, because it is a new execution.

### Filing indicator declarations and parameters

Configured per (entity, workflow). Three declaration states, in regulatory terms:

- **Required** — filed as reported; a required template with no facts is a
  validation failure.
- **Optional** — derived from the facts: reported if facts exist, not reported if
  they do not. The default.
- **Not required** — declared not filed; any facts for that template are excluded
  from the package, with a warning naming the template and the count excluded.

Like entities, these are live configuration. **A run freezes the declarations and
parameters it used.**

### Run / execution

A run is one execution of a submission instance. The instance is identified by
**entity + reporting date + snapshot + adjusted + version**, per workflow.

**Everything is frozen at execution time**: entity values (name, LEI, country,
scope), parameters, filing indicator declarations, the release binding, the input
file, the generated package, and the validation results. None of these are
resolved through live references after the fact.

**Re-execution supersedes within the instance.** Executing again creates a new
execution of the same instance; earlier executions remain in history. The latest
is prominent; earlier ones are visible beneath it.

**Deletion.** An individual execution can be deleted from its own page, with
confirmation. Deletion removes the run and its artifacts.
*Future constraint:* a signed-off execution can never be deleted.

**Failed executions remain visible in history.** A failure is a fact about what
happened and is part of the record.

---

## Dependency changes

Entities and taxonomy releases are the system's two live dependencies. Both may
change or be deleted at any time. History is immune; the future is not.

When a user attempts a **new execution** whose instance previously used a
dependency that has since changed or disappeared, the system **stops and requires
deliberate action**:

- Entity deleted → "The entity used for this execution no longer exists. Select a
  current entity to continue."
- Entity values changed → proceed with current values, but the change is visible
  in the execution record.
- Release deleted → "This instance previously used release 4.2, which no longer
  exists. Select a release to continue."
- Release artifact replaced → confirm before executing against changed inputs.

The system never silently substitutes a dependency and never silently proceeds
against a missing one.

---

## Interaction rules

**States.** Every screen defines its empty state, loading state, in-progress
state, and failure state. No screen renders a blank region while waiting.

**Progress.** Any operation exceeding a few seconds (DPM conversion, rule
ingestion, formula validation) shows progress where the user started it, names
what is happening in business terms, and remains legible if the user navigates
away and returns.

**Confirmation.** Destructive actions (deleting a release, an entity, an
execution) require explicit confirmation naming the object and what will be lost.

**Navigation.** Back always returns where the user came from. Deep links resolve.
Unknown routes render a styled page, never a developer error.

**Unsaved changes.** Leaving a form with unsaved edits warns before discarding.

**Vocabulary.** One verb per gesture across the whole app ("View", not
View/Open/Register interchangeably). Dates render as `DD MMM YYYY`. Statuses read
in business language (Successful, Failed, Running), never internal enum values.

**Errors.** Never expose internal identifiers, table names, stack traces, or file
paths. Every message names what went wrong, why, and what to do next. Where a
mistake has a likely cause, name it ("That's the full taxonomy — you need the item
starting 'Taxonomy package'").

---

## Storage and identity

Every stored artifact receives a system-generated storage key, unique per upload,
independent of the user's filename. The original filename is retained for display
and audit only. Nothing in the system keys behaviour, lookup, or paths off a
user-supplied name.

Checksums are used for integrity and duplicate **detection**, not identity.
Taxonomy artifacts may reject an exact duplicate, naming the release that already
uses it. Fact files may be uploaded repeatedly across entities, dates, and
re-executions without any duplicate error.

The database and the filesystem must agree. Reconciliation detects and reports
records without files and files without records.

---

## What "done" means

A feature is done when a reporting analyst can complete the task alone, without
help, without a terminal, and without being surprised — and when a reviewer can
later reconstruct exactly what happened and why.

Passing tests is necessary and not sufficient.
