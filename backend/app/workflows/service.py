"""Orchestration: the only place that composes the pipeline stages.

Run lifecycle: create → attach fact + indicators/params files (facts stage) →
execute (resolve facts against the bound snapshot+release+module via taxonomy →
build the package via generation → persist outputs). ``workflows`` is the sole
package allowed to import other stages.

The package's creation timestamp is derived deterministically from the run id +
reference date (never ``now()``), so a run's package is reproducible.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import SessionLocal
from app.core.errors import (
    ArtifactUnavailableError,
    ConflictError,
    DependencyChangedError,
    NotFoundError,
    ValidationError,
)
from app.facts import service as facts
from app.facts.models import Fact, RunFile, RunFileRole
from app.facts.parsers import default_indicators_params_parser
from app.facts.schemas import (
    FactIngestSummary,
    FilingIndicator,
    IndicatorsParams,
    IndicatorsParamsIngestSummary,
)
from app.generation import service as generation
from app.generation import xml_builder as generation_xml
from app.generation.schemas import (
    FactInput,
    FilingIndicatorSpec,
    OutputFormat,
    PackageMetadata,
)
from app.taxonomy import artifacts as taxonomy_artifacts
from app.taxonomy import capabilities as taxonomy_caps
from app.taxonomy import rules as taxonomy_rules
from app.taxonomy import service as taxonomy
from app.taxonomy.models import (
    ReleaseArtifact,
    SnapshotStatus,
    TaxonomySnapshot,
)
from app.taxonomy.service import normalize_template_code, template_of
from app.validation import register as validation_register
from app.validation import report as validation_report
from app.validation import service as validation
from app.validation.arelle_adapter import ArelleFormulaValidator, FormulaRun
from app.validation.models import Severity, ValidationFinding, ValidationPhase
from app.validation.schemas import Finding

# Filing-indicator declaration vocabulary. Optional = derive from facts
# (default, stored as absence); Required = positive indicator, run FAILS if no
# facts; Not required = negative + facts excluded. Lives in its own module so
# the data migration can share it.
from app.workflows.declarations import (
    DECLARATION_NOT_REQUIRED,
    DECLARATION_OPTIONAL,
    DECLARATION_REQUIRED,
)
from app.workflows.declarations import VALID_DECLARATIONS as _VALID_DECLARATIONS
from app.workflows.models import (
    WORKFLOW_CATEGORIES,
    Entity,
    EntityWorkflowConfig,
    RegulatorFormatDefault,
    Run,
    RunStatus,
    WorkflowConfig,
    WorkflowFormatConfig,
)

logger = logging.getLogger(__name__)

_ATTACHABLE = {RunStatus.created, RunStatus.files_attached}


def _normalize(code: str) -> str:
    return normalize_template_code(code, form="db")


def _validate_lei(entity: str) -> str:
    entity = entity.strip()
    if len(entity) != 20 or not entity.isalnum():
        raise ValidationError(
            f"malformed entity LEI {entity!r} (expected 20 alphanumeric chars)"
        )
    return entity.upper()


# --- workflow configs ------------------------------------------------------


def list_workflows(
    db: Session,
    *,
    active_only: bool = True,
    category: str | None = None,
) -> list[WorkflowConfig]:
    stmt = select(WorkflowConfig).order_by(WorkflowConfig.name)
    if active_only:
        stmt = stmt.where(WorkflowConfig.is_active.is_(True))
    if category is not None:
        stmt = stmt.where(WorkflowConfig.category == category)
    return list(db.scalars(stmt))


def get_workflow(db: Session, workflow_id: int) -> WorkflowConfig:
    wf = db.get(WorkflowConfig, workflow_id)
    if wf is None:
        raise NotFoundError(f"workflow id={workflow_id} not found")
    return wf


def update_workflow_settings(
    db: Session, workflow_id: int, *, category: str | None, is_active: bool
) -> WorkflowConfig:
    """Settings-page update: a workflow's category and active flag."""
    wf = get_workflow(db, workflow_id)
    if category is not None and category not in WORKFLOW_CATEGORIES:
        raise ValidationError(
            f"category must be one of {', '.join(WORKFLOW_CATEGORIES)} (or null)"
        )
    wf.category = category
    wf.is_active = is_active
    db.commit()
    db.refresh(wf)
    return wf


def last_run_for_workflow(db: Session, workflow_id: int) -> Run | None:
    """The most recent run for a workflow (for last-activity chips)."""
    return db.scalar(
        select(Run)
        .where(Run.workflow_id == workflow_id)
        .order_by(Run.id.desc())
        .limit(1)
    )


def category_summaries(db: Session) -> list[dict]:
    """Per-category active-suite count + most recent run (for the landing tiles)."""
    summaries: list[dict] = []
    for category in WORKFLOW_CATEGORIES:
        suites = list_workflows(db, category=category)
        last: Run | None = None
        for wf in suites:
            run = last_run_for_workflow(db, wf.id)
            if run is not None and (last is None or run.id > last.id):
                last = run
        summaries.append(
            {"category": category, "active_count": len(suites), "last_run": last}
        )
    return summaries


def suite_summaries(db: Session, category: str) -> list[dict]:
    """Active suites in a category, each with its most recent run."""
    return [
        {"workflow": wf, "last_run": last_run_for_workflow(db, wf.id)}
        for wf in list_workflows(db, category=category)
    ]


# --- run lifecycle ---------------------------------------------------------


def list_entities(db: Session) -> list[Entity]:
    return list(db.scalars(select(Entity).order_by(Entity.name)))


def get_entity(db: Session, entity_id: int) -> Entity:
    entity = db.get(Entity, entity_id)
    if entity is None:
        raise NotFoundError(f"entity id={entity_id} not found")
    return entity


def _clean_entity_fields(
    *, name: str, lei: str, country: str, default_scope: str
) -> dict:
    scope = default_scope.strip().upper()
    if scope not in {"IND", "CON"}:
        raise ValidationError("default_scope must be IND or CON")
    country = country.strip().upper()
    if len(country) != 2 or not country.isalpha():
        raise ValidationError("country must be a 2-letter ISO code")
    if not name.strip():
        raise ValidationError("name is required")
    return {
        "name": name.strip(),
        "lei": _validate_lei(lei),
        "country": country,
        "default_scope": scope,
    }


def create_entity(
    db: Session, *, name: str, lei: str, country: str, default_scope: str
) -> Entity:
    fields = _clean_entity_fields(
        name=name, lei=lei, country=country, default_scope=default_scope
    )
    if db.scalar(select(Entity).where(Entity.lei == fields["lei"])):
        raise ConflictError(f"an entity with LEI {fields['lei']} already exists")
    entity = Entity(**fields)
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return entity


def update_entity(
    db: Session,
    entity_id: int,
    *,
    name: str,
    lei: str,
    country: str,
    default_scope: str,
) -> Entity:
    entity = get_entity(db, entity_id)
    fields = _clean_entity_fields(
        name=name, lei=lei, country=country, default_scope=default_scope
    )
    clash = db.scalar(
        select(Entity).where(Entity.lei == fields["lei"], Entity.id != entity.id)
    )
    if clash is not None:
        raise ConflictError(f"an entity with LEI {fields['lei']} already exists")
    for key, value in fields.items():
        setattr(entity, key, value)
    db.commit()
    db.refresh(entity)
    return entity


def delete_entity(db: Session, entity_id: int) -> None:
    """Delete an entity — a live reference-data row (freely deletable).

    Its per-(entity, workflow) configuration is removed with it. Runs are
    unaffected: each froze the entity's values (name, LEI, scope, country) at
    execution and keeps them; the run's ``entity_id`` remains as historical
    provenance (now pointing at a deleted entity), so a later re-execution can
    detect the entity is gone and ask for a current one.
    """
    entity = get_entity(db, entity_id)
    db.execute(
        delete(EntityWorkflowConfig).where(
            EntityWorkflowConfig.entity_id == entity_id
        )
    )
    db.delete(entity)
    db.commit()
    logger.info("deleted entity id=%s", entity_id)


# --- per-(entity, workflow) configuration ----------------------------------


def get_entity_workflow_config(
    db: Session, entity_id: int, workflow_id: int
) -> EntityWorkflowConfig | None:
    return db.scalar(
        select(EntityWorkflowConfig).where(
            EntityWorkflowConfig.entity_id == entity_id,
            EntityWorkflowConfig.workflow_id == workflow_id,
        )
    )


def _clean_declarations(declarations: dict | None) -> dict[str, str]:
    """Normalise a template→declaration map: canonical codes, drop Optional/invalid.

    Only Required / Not required are stored (Optional is the absence of an
    entry), so the map stays compact and templates default to Optional.
    """
    out: dict[str, str] = {}
    for code, decl in (declarations or {}).items():
        value = str(decl).strip().lower()
        if value not in _VALID_DECLARATIONS or value == DECLARATION_OPTIONAL:
            continue
        try:
            # Declarations are keyed at template level (matching filing
            # indicators); a table code like C_73.00.a collapses to C_73.00.
            out[template_of(_normalize(code))] = value
        except ValueError:
            continue
    return out


def upsert_entity_workflow_config(
    db: Session,
    *,
    entity_id: int,
    workflow_id: int,
    indicator_declarations: dict | None,
    base_currency: str | None,
    decimals: int | None,
) -> EntityWorkflowConfig:
    get_entity(db, entity_id)  # 404 if unknown
    get_workflow(db, workflow_id)
    currency = (base_currency or "").strip().upper() or None
    if currency is not None and (len(currency) != 3 or not currency.isalpha()):
        raise ValidationError("base_currency must be a 3-letter ISO code")

    config = get_entity_workflow_config(db, entity_id, workflow_id)
    if config is None:
        config = EntityWorkflowConfig(
            entity_id=entity_id, workflow_id=workflow_id
        )
        db.add(config)
    config.indicator_declarations = _clean_declarations(indicator_declarations)
    config.base_currency = currency
    config.decimals = decimals
    db.commit()
    db.refresh(config)
    return config


# ---------------------------------------------------------------------------
# Output-format configuration (per regulator, per (regulator, workflow))
# ---------------------------------------------------------------------------

# The format used when no configuration says otherwise (EBA convention).
DEFAULT_OUTPUT_FORMAT = OutputFormat.xbrl_csv


def get_regulator_format_default(
    db: Session, regulator_id: int
) -> OutputFormat:
    """A regulator's configured default format, or the built-in default."""
    row = db.scalar(
        select(RegulatorFormatDefault).where(
            RegulatorFormatDefault.regulator_id == regulator_id
        )
    )
    return row.output_format if row is not None else DEFAULT_OUTPUT_FORMAT


def set_regulator_format_default(
    db: Session, *, regulator_id: int, output_format: OutputFormat
) -> OutputFormat:
    """Set (upsert) a regulator's default output format."""
    taxonomy.get_regulator(db, regulator_id)  # 404 if unknown
    row = db.scalar(
        select(RegulatorFormatDefault).where(
            RegulatorFormatDefault.regulator_id == regulator_id
        )
    )
    if row is None:
        row = RegulatorFormatDefault(regulator_id=regulator_id)
        db.add(row)
    row.output_format = output_format
    db.commit()
    return output_format


def get_workflow_format_override(
    db: Session, regulator_id: int, workflow_id: int
) -> OutputFormat | None:
    """The per-(regulator, workflow) override format, if one is set."""
    row = db.scalar(
        select(WorkflowFormatConfig).where(
            WorkflowFormatConfig.regulator_id == regulator_id,
            WorkflowFormatConfig.workflow_id == workflow_id,
        )
    )
    return row.output_format if row is not None else None


def set_workflow_format_override(
    db: Session,
    *,
    regulator_id: int,
    workflow_id: int,
    output_format: OutputFormat,
) -> WorkflowFormatConfig:
    """Set (upsert) a per-(regulator, workflow) output-format override."""
    taxonomy.get_regulator(db, regulator_id)  # 404 if unknown
    get_workflow(db, workflow_id)  # 404 if unknown
    row = db.scalar(
        select(WorkflowFormatConfig).where(
            WorkflowFormatConfig.regulator_id == regulator_id,
            WorkflowFormatConfig.workflow_id == workflow_id,
        )
    )
    if row is None:
        row = WorkflowFormatConfig(
            regulator_id=regulator_id, workflow_id=workflow_id
        )
        db.add(row)
    row.output_format = output_format
    db.commit()
    db.refresh(row)
    return row


def clear_workflow_format_override(
    db: Session, *, regulator_id: int, workflow_id: int
) -> None:
    """Remove a per-(regulator, workflow) override so the default applies."""
    row = db.scalar(
        select(WorkflowFormatConfig).where(
            WorkflowFormatConfig.regulator_id == regulator_id,
            WorkflowFormatConfig.workflow_id == workflow_id,
        )
    )
    if row is not None:
        db.delete(row)
        db.commit()


def resolve_output_format(
    db: Session, *, regulator_id: int, workflow_id: int
) -> OutputFormat:
    """The effective output format for a (regulator, workflow): override wins,
    else the regulator default, else the built-in default."""
    override = get_workflow_format_override(db, regulator_id, workflow_id)
    if override is not None:
        return override
    return get_regulator_format_default(db, regulator_id)


def regulator_format(db: Session, regulator_id: int) -> OutputFormat:
    """A regulator's default format (404 if the regulator is unknown)."""
    taxonomy.get_regulator(db, regulator_id)
    return get_regulator_format_default(db, regulator_id)


def workflow_format(
    db: Session, regulator_id: int, workflow_id: int
) -> tuple[OutputFormat, bool, OutputFormat]:
    """A (regulator, workflow)'s (effective format, overridden?, default).

    404 if either the regulator or the workflow is unknown.
    """
    taxonomy.get_regulator(db, regulator_id)
    get_workflow(db, workflow_id)
    default = get_regulator_format_default(db, regulator_id)
    override = get_workflow_format_override(db, regulator_id, workflow_id)
    effective = override if override is not None else default
    return effective, override is not None, default


def list_module_templates(
    db: Session, workflow_id: int, snapshot_id: int
) -> list:
    """Templates composing a workflow's module in a release (for the config UI).

    Returns one entry per *template* (filing-indicator level): table variants
    (``C_73.00.a`` / ``C_73.00.w``) collapse to a single ``C_73.00`` so the
    declarations UI matches the regulatory object. Requires a ready release.
    """
    from app.taxonomy.schemas import TemplateInfo

    wf = get_workflow(db, workflow_id)
    snapshot = taxonomy.get_snapshot(db, snapshot_id)
    with taxonomy.open_lookup(snapshot) as lk:
        tables = lk.list_templates(wf.module_code)
    seen: dict[str, str] = {}
    for t in tables:
        tid = template_of(t.code)
        seen.setdefault(tid, t.name)
    return [
        TemplateInfo(code=tid, name=name) for tid, name in sorted(seen.items())
    ]


def _release_fingerprint(db: Session, snapshot: TaxonomySnapshot) -> str:
    """A content fingerprint of a release's artifacts.

    Combines the DPM database checksum with the checksums of every occupied
    artifact slot (taxonomy package, filing rules, samples), so replacing *any*
    artifact changes the fingerprint. Order-stable (slots sorted) so it is
    deterministic for the same set of files.
    """
    parts = [f"dpm:{snapshot.checksum or ''}"]
    artifacts = db.scalars(
        select(ReleaseArtifact)
        .where(ReleaseArtifact.snapshot_id == snapshot.id)
        .order_by(ReleaseArtifact.slot)
    )
    for art in artifacts:
        parts.append(f"{art.slot.value}:{art.checksum}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def create_run(
    db: Session,
    *,
    workflow_id: int,
    snapshot_id: int,
    reference_date: date,
    entity_id: int,
    snapshot_key: str | None = None,
    adjusted_key: str | None = None,
    version_key: str | None = None,
    base_currency: str | None = None,
    decimals: int | None = None,
    release_id: int | None = None,
    settings: Settings | None = None,
) -> Run:
    settings = settings or get_settings()
    wf = get_workflow(db, workflow_id)
    if not wf.is_active:
        raise ValidationError(f"workflow {wf.name!r} is not active")

    snapshot = taxonomy.get_snapshot(db, snapshot_id)
    # Reconcile with disk first so a stale "ready" surfaces as artifacts_missing.
    taxonomy.verify_snapshot(db, snapshot, settings=settings)
    if snapshot.status is SnapshotStatus.artifacts_missing:
        raise ValidationError(
            f"snapshot id={snapshot_id} artifacts are missing on disk — "
            "re-ingest the snapshot to recover"
        )
    if snapshot.status is not SnapshotStatus.ready:
        raise ValidationError(
            f"snapshot id={snapshot_id} is not ready "
            f"(status={snapshot.status.value})"
        )

    entity = get_entity(db, entity_id)
    # Scope comes from the entity record (no per-run input).
    run_scope = entity.default_scope.strip().upper()
    if run_scope not in {"IND", "CON"}:
        raise ValidationError(
            f"entity {entity.name!r} has an invalid default scope"
        )

    def _key(value: str | None) -> str | None:
        value = (value or "").strip()
        return value or None

    # Parameter defaults come from the entity+workflow config when the caller
    # doesn't specify them (blank ⇒ EUR / -3); the run still owns the values.
    ewc = get_entity_workflow_config(db, entity.id, wf.id)
    if base_currency is None and ewc is not None and ewc.base_currency:
        base_currency = ewc.base_currency
    if decimals is None and ewc is not None and ewc.decimals is not None:
        decimals = ewc.decimals
    currency = (base_currency or "EUR").strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValidationError("base_currency must be a 3-letter ISO code")

    with taxonomy.open_lookup(snapshot, settings=settings) as lk:
        rid = release_id if release_id is not None else lk.default_release_id()
        meta = lk.module_metadata(wf.module_code, release_id=rid)
        if meta is None:
            raise ValidationError(
                f"module {wf.module_code} is not in snapshot id={snapshot_id} "
                f"at release {rid}"
            )
        # Freeze the taxonomy version this run is bound to. The user selected a
        # module version; record the exact version + framework version so history
        # is reproducible even after later releases change what the module
        # provides, and so rule scoping uses this version, not a live one.
        run_module_version = meta.module_version
        run_framework_version = taxonomy.framework_version(lk.release_code(rid))

    # Capture the release's capability set at execution binding (reproducibility;
    # capabilities are otherwise derived on read).
    caps = taxonomy_caps.derive_capabilities(
        taxonomy_artifacts.list_slots(db, snapshot, settings=settings)
    )

    run = Run(
        workflow_id=wf.id,
        snapshot_id=snapshot.id,
        release_id=rid,
        reference_date=reference_date,
        entity_id=entity.id,
        # Entity values are frozen here and read from the run forever after — a
        # later rename/edit/deletion of the entity must never alter this run.
        entity_name=entity.name,
        entity_lei=_validate_lei(entity.lei),
        entity_scope=run_scope,
        country=entity.country.upper(),
        snapshot_key=_key(snapshot_key),
        adjusted_key=_key(adjusted_key),
        version_key=_key(version_key),
        base_currency=currency,
        decimals=decimals if decimals is not None else -3,
        status=RunStatus.created,
        capabilities=caps.to_dict(),
        module_version=run_module_version,
        framework_version=run_framework_version,
        release_fingerprint=_release_fingerprint(db, snapshot),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    logger.info(
        "created run id=%s workflow=%s entity=%s", run.id, wf.module_code,
        entity.lei, extra={"run_id": run.id},
    )
    return run


# The fields that identify a submission *instance* — a resubmission is a new
# execution sharing all of these (EBA Filing Rule 1.12, full resubmission).
INSTANCE_IDENTITY = (
    "workflow_id", "entity_id", "reference_date",
    "snapshot_key", "adjusted_key", "version_key",
)


def instance_identity(run: Run) -> tuple:
    """The tuple that groups a run's executions into one submission instance."""
    return tuple(getattr(run, f) for f in INSTANCE_IDENTITY)


def _entity_scope(entity: Entity) -> str:
    return entity.default_scope.strip().upper()


def detect_dependency_changes(
    db: Session, src: Run, *, settings: Settings | None = None
) -> list[dict]:
    """Changes to a run's live dependencies (entity, release) since it executed.

    Returns one ``{kind, message, ...}`` per entity/release dependency that has
    changed or disappeared relative to what ``src`` froze — empty if nothing
    changed. A new execution of the instance must surface these and get explicit
    confirmation before re-binding; it must never silently proceed.
    """
    settings = settings or get_settings()
    changes: list[dict] = []

    # --- entity ---------------------------------------------------------
    entity = (
        db.get(Entity, src.entity_id) if src.entity_id is not None else None
    )
    if entity is None:
        changes.append({
            "kind": "entity_deleted",
            "message": "The entity used for this execution no longer exists. "
            "Select a current entity to continue.",
        })
    else:
        diffs: list[str] = []
        if src.entity_name is not None and entity.name != src.entity_name:
            diffs.append(f"name ({src.entity_name} → {entity.name})")
        if _validate_lei(entity.lei) != src.entity_lei:
            diffs.append(f"LEI ({src.entity_lei} → {_validate_lei(entity.lei)})")
        if entity.country.upper() != src.country:
            diffs.append(f"country ({src.country} → {entity.country.upper()})")
        if _entity_scope(entity) != src.entity_scope:
            diffs.append(f"scope ({src.entity_scope} → {_entity_scope(entity)})")
        if diffs:
            changes.append({
                "kind": "entity_changed",
                "message": "The entity has changed since the last execution: "
                + ", ".join(diffs) + ". The new execution will use the current "
                "values.",
                "fields": diffs,
            })

    # --- release --------------------------------------------------------
    snapshot = db.get(TaxonomySnapshot, src.snapshot_id)
    if snapshot is None:
        changes.append({
            "kind": "release_deleted",
            "message": "The taxonomy release used for this execution no longer "
            "exists. Select a release to continue.",
        })
    else:
        taxonomy.verify_snapshot(db, snapshot, settings=settings)
        label = snapshot.display_name
        if snapshot.status is not SnapshotStatus.ready:
            changes.append({
                "kind": "release_unavailable",
                "message": f"The taxonomy release {label} is no longer usable "
                "(its files are missing). Re-ingest it or select a release to "
                "continue.",
            })
        elif (
            src.release_fingerprint is not None
            and _release_fingerprint(db, snapshot) != src.release_fingerprint
        ):
            changes.append({
                "kind": "release_changed",
                "message": f"An artifact of the taxonomy release {label} has "
                "been replaced since the last execution. The new execution will "
                "use the current files.",
            })

    return changes


# Change kinds detect_dependency_changes emits, grouped by dependency and by how
# they can be resolved before a new execution.
_ENTITY_CHANGE_KINDS = {"entity_deleted", "entity_changed"}
_RELEASE_CHANGE_KINDS = {"release_deleted", "release_unavailable", "release_changed"}
# A vanished dependency can only be resolved by choosing a current one; a changed
# but still-usable one may instead be acknowledged (proceed with current values).
_MUST_RESELECT_KINDS = {"entity_deleted", "release_deleted", "release_unavailable"}


def reexecute_run(
    db: Session,
    source_run_id: int,
    *,
    entity_id: int | None = None,
    release_snapshot_id: int | None = None,
    acknowledge_changes: bool = False,
    settings: Settings | None = None,
) -> Run:
    """Create a fresh execution of an existing instance (re-execute / resubmit).

    Append-only: a new ``Run`` is created carrying the source run's instance
    identity (reporting date, instance keys) and its parameters; the source run
    and all prior executions are untouched. The caller then attaches a new fact
    file and executes, exactly as for a first run.

    Before creating the new execution the instance's live dependencies (entity,
    release) are checked against what the source run froze. Any unresolved change
    raises ``DependencyChangedError`` (carrying the list) so the user acts
    deliberately rather than the system silently re-binding. A change is resolved
    by either:

    - **choosing a current dependency** — ``entity_id`` selects a replacement
      entity, ``release_snapshot_id`` a replacement release; or
    - **acknowledging** (``acknowledge_changes=True``) — allowed only for a
      dependency that changed but is *still usable*; a *vanished* dependency
      (deleted entity / deleted or unusable release) must be reselected.
    """
    settings = settings or get_settings()
    src = get_run(db, source_run_id)

    changes = detect_dependency_changes(db, src, settings=settings)
    overrode_entity = entity_id is not None
    overrode_release = release_snapshot_id is not None
    unresolved = [
        c
        for c in changes
        if not (
            (c["kind"] in _ENTITY_CHANGE_KINDS and overrode_entity)
            or (c["kind"] in _RELEASE_CHANGE_KINDS and overrode_release)
            or (c["kind"] not in _MUST_RESELECT_KINDS and acknowledge_changes)
        )
    ]
    if unresolved:
        raise DependencyChangedError(
            "The entity or taxonomy release for this instance is no longer usable "
            "or has changed. Choose a current one (or confirm the change) to "
            "continue.",
            details=unresolved,
        )

    # Effective dependencies: an override wins, else the source run's. Choosing a
    # new release lets create_run pick that snapshot's current release id.
    eff_entity_id = entity_id if overrode_entity else src.entity_id
    eff_snapshot_id = release_snapshot_id if overrode_release else src.snapshot_id
    eff_release_id = None if overrode_release else src.release_id

    new_run = create_run(
        db,
        workflow_id=src.workflow_id,
        snapshot_id=eff_snapshot_id,
        reference_date=src.reference_date,
        entity_id=eff_entity_id,
        snapshot_key=src.snapshot_key,
        adjusted_key=src.adjusted_key,
        version_key=src.version_key,
        base_currency=src.base_currency,
        decimals=src.decimals,
        release_id=eff_release_id,
        settings=settings,
    )
    logger.info(
        "re-executing instance from run id=%s → new run id=%s",
        src.id, new_run.id, extra={"run_id": new_run.id},
    )
    return new_run


def get_run(db: Session, run_id: int) -> Run:
    run = db.get(Run, run_id)
    if run is None:
        raise NotFoundError(f"run id={run_id} not found")
    return run


def delete_run(
    db: Session, run_id: int, *, settings: Settings | None = None
) -> None:
    """Delete an execution and everything it produced.

    Removes the run's facts, validation findings, and stored files (rows + the
    on-disk directory), then the run itself. Other executions of the same
    instance are untouched. (When sign-off lands, a signed-off run can never be
    deleted — a future guard.)

    A run that is still in progress cannot be deleted — deleting mid-execution
    would race the work writing back to it. The caller is asked to wait.
    """
    settings = settings or get_settings()
    run = get_run(db, run_id)  # 404 if unknown
    if run.status in (
        RunStatus.running, RunStatus.formula_validation_running
    ):
        raise ConflictError(
            "This execution is still running — wait for it to finish before "
            "deleting it."
        )
    db.execute(delete(Fact).where(Fact.run_id == run_id))
    db.execute(delete(ValidationFinding).where(ValidationFinding.run_id == run_id))
    db.execute(delete(RunFile).where(RunFile.run_id == run_id))
    db.execute(delete(Run).where(Run.id == run_id))
    db.commit()
    facts.remove_run_dir(settings, run_id)
    logger.info("deleted run id=%s", run_id)


def list_runs(db: Session, workflow_id: int) -> list[Run]:
    return list(
        db.scalars(
            select(Run)
            .where(Run.workflow_id == workflow_id)
            .order_by(Run.id.desc())
        )
    )


def _require_attachable(run: Run) -> None:
    if run.status not in _ATTACHABLE:
        raise ValidationError(
            f"run id={run.id} is {run.status.value}; files can only be attached "
            "before execution"
        )


def attach_fact_file(
    db: Session,
    *,
    run_id: int,
    filename: str,
    data: bytes,
    settings: Settings | None = None,
) -> FactIngestSummary:
    run = get_run(db, run_id)
    _require_attachable(run)
    summary = facts.ingest_fact_file(
        db,
        run_id=run.id,
        entity=run.entity_lei,
        reference_date=run.reference_date,
        filename=filename,
        data=data,
        normalize=_normalize,
        settings=settings,
    )
    if run.status is RunStatus.created:
        run.status = RunStatus.files_attached
        db.commit()
    return summary


def attach_indicators_params_file(
    db: Session,
    *,
    run_id: int,
    filename: str,
    data: bytes,
    settings: Settings | None = None,
) -> IndicatorsParamsIngestSummary:
    run = get_run(db, run_id)
    _require_attachable(run)
    return facts.ingest_indicators_params_file(
        db,
        run_id=run.id,
        filename=filename,
        data=data,
        normalize=_normalize,
        settings=settings,
    )


def _creation_timestamp(run: Run) -> str:
    """Deterministic 17-digit YYYYMMDDhhmmssfff from reference date + run id.

    Not a real wall-clock time — determinism (byte-identical packages) forbids
    ``now()``. For real remittance the actual creation time would be used.
    """
    return f"{run.reference_date:%Y%m%d}{run.id % 1_000_000_000:09d}"


def _load_params(settings: Settings, run_file: RunFile) -> IndicatorsParams:
    data = (settings.data_dir / run_file.storage_key).read_bytes()
    result = default_indicators_params_parser.parse(data, normalize=_normalize)
    if result.errors or result.params is None:
        raise ValidationError(
            "indicators/parameters file no longer parses",
            details=[e.model_dump() for e in result.errors],
        )
    return result.params


def _resolve_declaration(
    template: str, declarations: dict[str, str], closed_with_facts: set[str]
) -> bool:
    """Whether a template is reported, honouring its filing-indicator declaration.

    Optional (default): reported iff it has closed, resolvable facts. Required:
    forced positive. Not required: forced negative.
    """
    decl = declarations.get(template, DECLARATION_OPTIONAL)
    if decl == DECLARATION_REQUIRED:
        return True
    if decl == DECLARATION_NOT_REQUIRED:
        return False
    return template in closed_with_facts


def _derive_indicators_params(
    run: Run,
    module_templates: set[str],
    closed_with_facts: set[str],
    declarations: dict[str, str],
) -> IndicatorsParams:
    """Derive indicators & parameters in-system from the run + its facts.

    Filing indicators are per **template** (the EBA regulatory object): a
    module's table variants (``C_73.00.a`` / ``C_73.00.w``) collapse to one
    ``C_73.00`` indicator, reported per its declaration (Optional/Required/Not
    required, where Optional = any of its table variants has facts). The
    template-level ids are what the taxonomy's assertion preconditions key on
    (Filing Rule 1.6).
    """
    template_ids = {template_of(t) for t in module_templates}
    with_facts = {template_of(t) for t in closed_with_facts}
    return IndicatorsParams(
        filing_indicators=[
            FilingIndicator(
                template_code=tid,
                reported=_resolve_declaration(tid, declarations, with_facts),
            )
            for tid in sorted(template_ids)
        ],
        entity_lei=run.entity_lei,
        reference_date=run.reference_date,
        base_currency=run.base_currency,
        decimals=run.decimals,
    )


def _template_level_indicators(
    indicators: list[FilingIndicator],
) -> list[FilingIndicator]:
    """Collapse filing indicators to template level (dedupe table variants).

    ``reported`` for a template is the OR over its table variants, so a template
    is positive if any of its variants is. Idempotent for already template-level
    indicators.
    """
    merged: dict[str, bool] = {}
    for fi in indicators:
        tid = template_of(fi.template_code)
        merged[tid] = merged.get(tid, False) or fi.reported
    return [
        FilingIndicator(template_code=tid, reported=rep)
        for tid, rep in sorted(merged.items())
    ]


def _load_declarations(db: Session, run: Run) -> dict[str, str]:
    """The entity+workflow filing-indicator declarations for a run (canonical)."""
    if run.entity_id is None:
        return {}
    ewc = get_entity_workflow_config(db, run.entity_id, run.workflow_id)
    return dict(ewc.indicator_declarations) if ewc else {}


def _not_filed_findings(
    fact_rows, module_templates: set[str], declarations: dict[str, str]
) -> tuple[set[str], list[Finding]]:
    """Templates declared not-required, and a warning per one that has facts.

    Works at template level: a declaration on ``C_73.00`` excludes facts for all
    of its table variants. Returns ``(excluded_template_ids, findings)``.
    """
    excluded = {
        tid
        for tid in {template_of(t) for t in module_templates}
        if declarations.get(tid) == DECLARATION_NOT_REQUIRED
    }
    findings: list[Finding] = []
    for template in sorted(excluded):
        n = sum(1 for f in fact_rows if template_of(f.template_code) == template)
        if n:
            findings.append(
                Finding(
                    severity=Severity.warning,
                    phase=ValidationPhase.pre_generation,
                    code="TEMPLATE_DECLARED_NOT_FILED",
                    message=f"template {template} declared not required; "
                    f"{n} facts excluded",
                    template_code=template,
                )
            )
    return excluded, findings


def _required_empty_findings(
    module_templates: set[str],
    declarations: dict[str, str],
    with_facts: set[str],
) -> tuple[set[str], list[Finding]]:
    """Templates declared Required that carry no facts — a blocking error each.

    A Required template must be filed; an empty one fails the run. Returns
    ``(required_empty_template_ids, findings)`` — the ids let the downstream
    empty-indicator warning skip these (they are already errored).
    """
    required_empty = {
        tid
        for tid in {template_of(t) for t in module_templates}
        if declarations.get(tid) == DECLARATION_REQUIRED and tid not in with_facts
    }
    findings = [
        Finding(
            severity=Severity.error,
            phase=ValidationPhase.pre_generation,
            code="REQUIRED_TEMPLATE_EMPTY",
            message=f"template {template} is declared required but has no facts; "
            "a required template must be filed",
            template_code=template,
        )
        for template in sorted(required_empty)
    ]
    return required_empty, findings


def _safe_validate(what: str, fn) -> list[Finding]:
    """Run a validator; a crash becomes a finding, never a failed run."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 — validation must never crash a run
        logger.exception("validator %s raised", what)
        return [
            Finding(
                severity=Severity.error,
                phase=ValidationPhase.pre_generation,
                code="VALIDATOR_ERROR",
                message=f"the {what} validator raised: {exc}",
            )
        ]


def _persist_findings(
    db: Session, run_id: int, findings: list[Finding]
) -> None:
    # Re-execute replaces the prior run's findings.
    db.query(ValidationFinding).filter(ValidationFinding.run_id == run_id).delete()
    db.add_all(
        ValidationFinding(run_id=run_id, **f.model_dump()) for f in findings
    )
    db.commit()


def list_findings(db: Session, run_id: int) -> list[ValidationFinding]:
    return list(
        db.scalars(
            select(ValidationFinding)
            .where(ValidationFinding.run_id == run_id)
            .order_by(ValidationFinding.severity, ValidationFinding.id)
        )
    )


def _report_identity(
    db: Session, run: Run, wf: WorkflowConfig, package_filename: str
) -> list[tuple[str, str]]:
    """Run identity label/value pairs for the report header."""
    # Frozen at execution — read from the run, never resolved live (a later
    # rename/deletion of the entity must not alter this historical report).
    entity_name = run.entity_name or run.entity_lei
    snapshot = db.get(TaxonomySnapshot, run.snapshot_id)
    release_label = snapshot.version_label if snapshot is not None else str(
        run.release_id
    )
    return [
        ("Run", f"#{run.id}"),
        ("Suite", f"{wf.name} ({wf.module_code})"),
        ("Entity", f"{entity_name} · {run.entity_lei}.{run.entity_scope}"),
        ("Reporting date", run.reference_date.isoformat()),
        ("Snapshot key", run.snapshot_key or "—"),
        ("Adjusted key", run.adjusted_key or "—"),
        ("Version key", run.version_key or "—"),
        ("Taxonomy release", release_label),
        ("Package", package_filename),
    ]


def _append_findings(db: Session, run_id: int, findings: list[Finding]) -> None:
    db.add_all(
        ValidationFinding(run_id=run_id, **f.model_dump()) for f in findings
    )
    db.commit()


def _run_module_scope(db: Session, run: Run) -> tuple[str | None, str | None]:
    """The (module_code, framework_version) a run's rules are scoped to. The
    module comes from the workflow; the framework version is frozen on the run.
    Either may be None (legacy runs before the version-freeze) → no scoping."""
    wf = db.get(WorkflowConfig, run.workflow_id)
    module_code = wf.module_code if wf is not None else None
    return module_code, run.framework_version


def _register_rule_meta(db: Session, run: Run) -> dict | None:
    """Workbook facts for the run's register, resolved for its reporting date.

    ``{"descriptions": {...}, "inactive": {...}}`` from the release's ingested
    validation rules, scoped to the run's module version. ``None`` when no
    workbook is ingested. Never raises — the register renders without it.
    """
    try:
        if not taxonomy_rules.has_ingested_rules(db, run.snapshot_id):
            return None
        module_code, framework_version = _run_module_scope(db, run)
        view = taxonomy_rules.build_register_view(
            db, run.snapshot_id, run.reference_date,
            module_code=module_code, framework_version=framework_version,
        )
        return {"descriptions": view.descriptions, "inactive": view.inactive}
    except Exception:  # noqa: BLE001 — the register must render regardless
        logger.exception(
            "run id=%s: could not load validation-rules register meta", run.id,
            extra={"run_id": run.id},
        )
        return None


def build_run_register(db: Session, run: Run, findings: list) -> list:
    """The run's rule register, with workbook descriptions joined in."""
    return validation_register.build_register(
        findings, run.formula_summary, rule_meta=_register_rule_meta(db, run)
    )


def _rule_scope_statement(run: Run) -> str | None:
    """Plain-language statement of the rule set applied, e.g.
    "1,284 rules applicable to COREP_LCR_DA 3.3.0 at 31 Dec 2025"."""
    scope = run.rule_scope
    if not scope:
        return None
    count = scope.get("count", 0)
    module = scope.get("module_code") or ""
    version = scope.get("module_version") or ""
    try:
        when = date.fromisoformat(scope["reference_date"]).strftime("%d %b %Y")
    except (KeyError, ValueError):
        when = run.reference_date.strftime("%d %b %Y")
    module_bit = f" to {module} {version}".rstrip() if module else ""
    return f"{count:,} rules applicable{module_bit} at {when}"


def _write_validation_report(
    db: Session,
    run: Run,
    wf: WorkflowConfig,
    package_filename: str,
    *,
    settings: Settings,
) -> None:
    """(Re)write the validation report from all persisted findings for the run.

    Upserts the report in place (stable ``RunFile`` id) so a download link a
    client already holds stays valid when the report is rewritten after the
    formula-validation phase.
    """
    findings = list_findings(db, run.id)  # ORM rows duck-type the Finding shape
    report = validation_report.build_report_html(
        identity=_report_identity(db, run, wf, package_filename),
        register=build_run_register(db, run, findings),
        formula=run.formula_summary,
        scope_statement=_rule_scope_statement(run),
    )
    facts.upsert_run_file(
        db,
        run_id=run.id,
        role=RunFileRole.validation_report,
        filename=f"validation_report_run{run.id}.html",
        data=report.encode("utf-8"),
        settings=settings,
    )
    db.commit()


def _finalise_status(db: Session, run: Run) -> None:
    has_errors = any(
        f.severity is Severity.error for f in list_findings(db, run.id)
    )
    run.status = (
        RunStatus.failed_validation if has_errors else RunStatus.generated
    )
    db.commit()


def _plural(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def run_verdict(run: Run, findings: list, formula_summary: dict | None) -> dict:
    """The submission verdict + the reasoning behind it, for the status banner.

    Blocking vs non-blocking derives from finding severity (structural error, or
    a formula rule the workbook marks ``error``); non-blocking rule failures are
    formula-phase warnings; warnings are the remaining warning-severity findings.
    A run is submittable iff there are zero blocking errors. Where a failing
    formula rule's severity is unknown (no workbook), it is counted honestly and
    the verdict says so rather than implying it is safe.
    """
    blocking = non_blocking_failures = warnings = 0
    for f in findings:
        phase = getattr(f.phase, "value", f.phase)
        if f.severity is Severity.error:
            blocking += 1
        elif f.severity is Severity.warning:
            if phase == "formula":
                non_blocking_failures += 1
            else:
                warnings += 1

    unknown_severity = 0
    if formula_summary and formula_summary.get("status") == "executed":
        unknown_severity = sum(
            1
            for r in formula_summary.get("rules", [])
            if r.get("result") == "FAILED" and not r.get("severity")
        )

    in_progress = run.status in (
        RunStatus.running, RunStatus.formula_validation_running
    )
    if in_progress:
        label, submittable = "Validating", None
    elif run.status is RunStatus.failed:
        label, submittable = "Run failed", False
    else:
        submittable = blocking == 0
        label = "Submittable" if submittable else "Not submittable"

    parts = [_plural(blocking, "blocking error")]
    parts.append(_plural(non_blocking_failures, "non-blocking rule failure"))
    if warnings:
        parts.append(_plural(warnings, "warning"))
    if unknown_severity:
        parts.append(f"{unknown_severity} of unknown severity")
    reasoning = " · ".join(parts)

    return {
        "label": label,
        "submittable": submittable,
        "blocking": blocking,
        "non_blocking_failures": non_blocking_failures,
        "warnings": warnings,
        "unknown_severity": unknown_severity,
        "severity_known": unknown_severity == 0,
        "reasoning": reasoning,
        "status": run.status.value,
    }


class _XmlResolution:
    """Adapts a taxonomy ``DatapointResolution`` + ``XmlSignature`` to the
    ``XmlResolver`` contract the xBRL-XML builder expects (metric + members +
    datatype code). Purely a shape adapter — no logic."""

    __slots__ = ("metric", "members", "datatype_code")

    def __init__(self, sig, datatype_code: str) -> None:
        self.metric = sig.metric
        self.members = sig.members
        self.datatype_code = datatype_code


def _make_xml_resolver(lk, resolve, release_id: int):
    """An ``XmlResolver`` combining the (template,row,col) datatype resolve with
    the datapoint's xBRL-XML signature (metric + scenario). Returns ``None`` for
    a fact whose datapoint has no XML signature (e.g. a typed/open-table key),
    so the builder treats it exactly like an unresolved fact."""

    def _xml_resolve(t, r, c):
        res = resolve(t, r, c)
        if res is None or res.property_id is None:
            return None
        sig = lk.xml_signature(
            res.property_id, res.context_id, release_id=release_id
        )
        if sig is None:
            return None
        return _XmlResolution(sig, res.datatype_code)

    return _xml_resolve


def execute_run(
    db: Session, run_id: int, *, settings: Settings | None = None
) -> Run:
    settings = settings or get_settings()
    run = get_run(db, run_id)
    if run.status is RunStatus.running:
        raise ValidationError(f"run id={run_id} is already running")

    files = facts.list_run_files(db, run.id)
    fact_files = [f for f in files if f.role is RunFileRole.fact_input]
    # Indicators/parameters are derived in-system by default; an uploaded file is
    # an optional "advanced" override.
    ind_files = [f for f in files if f.role is RunFileRole.indicators_params]
    if not fact_files:
        raise ValidationError("no fact file attached to this run")

    run.status = RunStatus.running
    run.error = None
    run.failure_details = None
    db.commit()
    logger.info("executing run id=%s", run.id, extra={"run_id": run.id})

    try:
        wf = get_workflow(db, run.workflow_id)
        snapshot = taxonomy.get_snapshot(db, run.snapshot_id)
        fact_rows = facts.list_facts(db, run.id, limit=1_000_000)
        findings: list[Finding] = []

        with taxonomy.open_lookup(snapshot, settings=settings) as lk:
            meta = lk.module_metadata(wf.module_code, release_id=run.release_id)
            if meta is None:
                raise ValidationError(
                    f"module {wf.module_code} is not in the bound snapshot"
                )
            module_templates = {
                t.code
                for t in lk.list_templates(
                    wf.module_code, release_id=run.release_id
                )
            }
            open_templates = lk.open_templates(
                wf.module_code, release_id=run.release_id
            )

            def resolve(t, r, c):
                return lk.resolve(t, r, c, release_id=run.release_id)

            # Filing-indicator declarations (Auto/True/False) for this entity +
            # workflow. Templates declared not-filed (False) are excluded from
            # the package, with a warning per template that had facts.
            declarations = _load_declarations(db, run)
            excluded_templates, exclusion_findings = _not_filed_findings(
                fact_rows, module_templates, declarations
            )
            findings += exclusion_findings
            active_facts = [
                f
                for f in fact_rows
                if template_of(f.template_code) not in excluded_templates
            ]

            # Which closed templates actually have resolvable facts, and their
            # datatypes (drives derived filing indicators + parameters).
            closed_with_facts: set[str] = set()
            datatypes_present: set[str] = set()
            for f in active_facts:
                if f.template_code in open_templates:
                    continue
                res = resolve(f.template_code, f.row_code, f.column_code)
                if res is not None:
                    closed_with_facts.add(f.template_code)
                    datatypes_present.add(res.datatype_code)

            # A template declared Required but carrying no facts fails the run.
            required_empty, required_findings = _required_empty_findings(
                module_templates,
                declarations,
                {template_of(t) for t in closed_with_facts},
            )
            findings += required_findings

            # Indicators & parameters: uploaded override, else derived in-system.
            if ind_files:
                params = _load_params(settings, ind_files[-1])
            else:
                params = _derive_indicators_params(
                    run, module_templates, closed_with_facts, declarations
                )
            # Filing indicators are always rendered at template level (the EBA
            # regulatory object; Filing Rule 1.6). Collapse table variants so an
            # uploaded override is normalised the same way as derivation.
            params.filing_indicators = _template_level_indicators(
                params.filing_indicators
            )

            # Persist the filing-indicator outcomes for traceability — which
            # templates report and why (an explicit declaration, or derived).
            run.filing_indicators = [
                {
                    "template_code": fi.template_code,
                    "reported": fi.reported,
                    "source": (
                        "declared"
                        if ind_files
                        or declarations.get(fi.template_code)
                        in (DECLARATION_REQUIRED, DECLARATION_NOT_REQUIRED)
                        else "auto"
                    ),
                }
                for fi in params.filing_indicators
            ]

            # Phase 1 — pre-generation checks on the facts (excluding not-filed
            # templates, so a declared-not-filed template with facts doesn't trip
            # the missing-indicator rule).
            findings += _safe_validate(
                "facts",
                lambda: validation.validate_facts(
                    facts=active_facts,
                    resolve=resolve,
                    module_templates=module_templates,
                    open_templates=open_templates,
                    filing_indicators=params.filing_indicators,
                    fact_file_name=fact_files[-1].filename,
                    entity_id=run.entity_lei,
                    ref_period=run.reference_date,
                    template_of=template_of,
                    required_empty=required_empty,
                ),
            )

            metadata = PackageMetadata(
                entity_lei=run.entity_lei,
                scope=run.entity_scope,
                country=run.country,
                reference_date=run.reference_date,
                creation_timestamp=_creation_timestamp(run),
                framework_code=wf.framework_code,
                module_code=wf.module_code,
                module_version=meta.module_version,
                taxonomy_version=lk.release_code(run.release_id) or "",
                base_currency=params.base_currency,
                decimals=params.decimals,
                filing_indicators=[
                    FilingIndicatorSpec(
                        template_code=fi.template_code, reported=fi.reported
                    )
                    for fi in params.filing_indicators
                ],
            )
            # Exclude open-table facts (guarded as findings) so we never emit a
            # malformed CSV; lenient build skips unresolved facts too. Not-filed
            # templates are already gone from active_facts.
            generatable = [
                FactInput(
                    template_code=f.template_code,
                    row_code=f.row_code,
                    column_code=f.column_code,
                    value=f.value,
                )
                for f in active_facts
                if f.template_code not in open_templates
            ]
            # Dispatch on the (regulator, workflow) output format. Both builders
            # take the same facts + metadata; only the serialisation differs.
            output_format = resolve_output_format(
                db,
                regulator_id=snapshot.regulator_id,
                workflow_id=run.workflow_id,
            )
            run.output_format = output_format
            if output_format is OutputFormat.xbrl_xml:
                package = generation_xml.build_xml_instance(
                    generatable,
                    metadata,
                    resolve=_make_xml_resolver(lk, resolve, run.release_id),
                    strict=False,
                )
            else:
                package = generation.build_package(
                    generatable, metadata, resolve=resolve, strict=False
                )

        # Phase 2 — post-generation structural checks, specific to the output
        # format. The xBRL-CSV package check-set understands the CSV package
        # layout only and must not run against a single-file xBRL-XML instance;
        # the XML instance gets its own check-set (docs/xml-notes.md §9).
        if output_format is OutputFormat.xbrl_xml:
            findings += _safe_validate(
                "package",
                lambda: validation.validate_xml_instance(
                    package_bytes=package.content,
                    package_filename=package.filename,
                    filing_indicators=metadata.filing_indicators,
                ),
            )
        else:
            findings += _safe_validate(
                "package",
                lambda: validation.validate_package(
                    package_bytes=package.content,
                    package_filename=package.filename,
                    datatypes_present=datatypes_present,
                ),
            )

        def _store(session, rid, filename, data, role=RunFileRole.package_output):
            return facts.store_run_file(
                session, run_id=rid, role=role, filename=filename, data=data,
                settings=settings,
            )

        # Persist structural findings, the package (always), and the report.
        _persist_findings(db, run.id, findings)
        generation.store_package(db, run_id=run.id, package=package, store=_store)
        _write_validation_report(
            db, run, wf, package.filename, settings=settings
        )

        # Formula validation (Arelle) runs as a distinct background phase when
        # enabled and a taxonomy package is available; otherwise finalise now.
        if settings.arelle_enabled and taxonomy.snapshot_taxonomy_packages(
            settings, run.snapshot_id
        ):
            run.status = RunStatus.formula_validation_running
            db.commit()
            logger.info(
                "run id=%s structural done; formula validation queued",
                run.id, extra={"run_id": run.id},
            )
        else:
            _finalise_status(db, run)
            logger.info(
                "run id=%s %s (%d findings)", run.id, run.status.value,
                len(findings), extra={"run_id": run.id},
            )
    except ValidationError as exc:
        run.status = RunStatus.failed
        run.error = exc.message
        run.failure_details = exc.details
        db.commit()
        logger.warning(
            "run id=%s failed: %s", run.id, exc.message, extra={"run_id": run.id}
        )
    except Exception as exc:  # noqa: BLE001 — record any failure on the run
        run.status = RunStatus.failed
        run.error = str(exc)
        db.commit()
        logger.exception(
            "run id=%s failed unexpectedly", run.id, extra={"run_id": run.id}
        )

    db.refresh(run)
    return run


def _build_formula_summary(
    run: FormulaRun, severities: dict[str, str] | None = None
) -> dict:
    """Summarise a formula-validation run for the register + report.

    Carries the per-rule results the adapter captured — per-evaluation detail
    (cell refs + compared values), the satisfied/not-satisfied counts, the EBA
    severity (blocking vs non-blocking, from the workbook), and the loaded/
    evaluated counts + deactivated-rules note.
    """
    severities = severities or {}
    if not run.available:
        return {
            "status": "unavailable",
            "loaded": 0,
            "evaluated": 0,
            "unsatisfied": 0,
            "satisfied": 0,
            "rules": [],
            "deactivated": run.deactivated,
            "note": run.unavailable_reason,
        }
    rules = [
        {
            "rule_id": r.rule_id,
            "assertion_type": r.assertion_type,
            "satisfied": r.satisfied,
            "not_satisfied": r.not_satisfied,
            "result": r.result,
            "values": r.values,
            "message": r.message,
            # EBA severity (from the workbook) → blocking iff "error". None when
            # unknown (no workbook / rule absent), surfaced honestly downstream.
            "severity": severities.get(r.rule_id),
            "blocking": severities.get(r.rule_id) == "error",
            "evaluations": r.evaluations,
        }
        for r in run.rule_results
    ]
    unsatisfied = sum(1 for r in run.rule_results if r.result == "FAILED")
    satisfied = sum(1 for r in run.rule_results if r.result == "PASSED")
    return {
        "status": "executed",
        "loaded": run.loaded,
        "evaluated": len(run.rule_results),
        "unsatisfied": unsatisfied,
        "satisfied": satisfied,
        "rules": rules,
        "deactivated": run.deactivated,
        "note": None,
    }


def _apply_workbook_severity(
    finding: Finding, severities: dict[str, str]
) -> Finding:
    """Re-key a formula finding's severity to the EBA workbook severity.

    A failing rule the workbook marks ``error`` becomes a blocking (error)
    finding — so it flows through ``_finalise_status`` and the verdict as
    blocking — while ``warning`` rules stay non-blocking. Unknown severity keeps
    whatever Arelle logged.
    """
    sev = severities.get(finding.code)
    if sev == "error":
        return finding.model_copy(update={"severity": Severity.error})
    if sev == "warning":
        return finding.model_copy(update={"severity": Severity.warning})
    return finding


def run_formula_validation_task(run_id: int) -> None:
    """Background: run Arelle formula validation and finalise the run.

    Distinct phase after structural. Never crashes the run — the adapter turns
    any failure into a non-blocking finding.
    """
    settings = get_settings()
    with SessionLocal() as db:
        run = db.get(Run, run_id)
        if run is None or run.status is not RunStatus.formula_validation_running:
            return
        wf = get_workflow(db, run.workflow_id)
        outputs = [
            f
            for f in facts.list_run_files(db, run.id)
            if f.role is RunFileRole.package_output
        ]
        if not outputs:
            _finalise_status(db, run)
            return
        package_path = settings.data_dir / outputs[-1].storage_key
        taxo = taxonomy.snapshot_taxonomy_packages(settings, run.snapshot_id)

        logger.info(
            "run id=%s formula validation started", run.id,
            extra={"run_id": run.id},
        )
        # Resolve the ingested workbook once for this reporting date: it drives
        # deactivation (IsActive + window, replacing the hardcoded two-rule list)
        # AND the per-rule EBA severity (blocking vs non-blocking).
        deactivated: set[str] | None = None
        severities: dict[str, str] = {}
        rule_scope: dict | None = None
        try:
            if taxonomy_rules.has_ingested_rules(db, run.snapshot_id):
                module_code, framework_version = _run_module_scope(db, run)
                view = taxonomy_rules.build_register_view(
                    db, run.snapshot_id, run.reference_date,
                    module_code=module_code, framework_version=framework_version,
                )
                deactivated = view.deactivated_codes
                severities = view.severities
                # Freeze the rule set applied, so the report can state it plainly.
                rule_scope = {
                    "count": view.applicable_count,
                    "module_code": module_code,
                    "module_version": run.module_version,
                    "framework_version": framework_version,
                    "reference_date": run.reference_date.isoformat(),
                }
        except Exception:  # noqa: BLE001 — fall back to the default list
            logger.exception(
                "run id=%s: workbook rule load failed", run.id,
                extra={"run_id": run.id},
            )
        validator = ArelleFormulaValidator(
            cache_dir=settings.data_dir / "cache",
            deactivated_rules=deactivated,
        )
        result = validator.validate_detailed(package_path, taxo)  # never raises

        # The Arelle call is long (~minutes). The run may have been deleted (or
        # otherwise finalised) while it ran; re-check before writing anything
        # back so a delete mid-window can't orphan findings or resurrect the run.
        db.expire_all()
        run = db.get(Run, run_id)
        if run is None or run.status is not RunStatus.formula_validation_running:
            logger.info(
                "run id=%s no longer awaiting formula results (deleted or "
                "finalised); discarding", run_id, extra={"run_id": run_id},
            )
            return

        # Re-key formula finding severities to the authoritative EBA workbook
        # severity, so an error-severity rule that fails blocks submission.
        findings = [_apply_workbook_severity(f, severities) for f in result.findings]

        run.formula_summary = _build_formula_summary(result, severities)
        if rule_scope is not None:
            run.rule_scope = rule_scope
        _append_findings(db, run.id, findings)
        _write_validation_report(
            db, run, wf, outputs[-1].filename, settings=settings
        )
        _finalise_status(db, run)
        logger.info(
            "run id=%s formula validation done: %s (%d formula findings)",
            run.id, run.status.value, len(findings), extra={"run_id": run.id},
        )


# --- run files -------------------------------------------------------------


def run_files(db: Session, run_id: int) -> list[RunFile]:
    get_run(db, run_id)  # 404 if the run doesn't exist
    return facts.list_run_files(db, run_id)


def get_run_file(db: Session, run_file_id: int) -> RunFile:
    run_file = db.get(RunFile, run_file_id)
    if run_file is None:
        raise NotFoundError(f"run file id={run_file_id} not found")
    return run_file


def run_file_available(settings: Settings, run_file: RunFile) -> bool:
    """Whether a run file's stored bytes are present at the storage root."""
    return facts.run_file_present(settings, run_file)


def run_file_size(settings: Settings, run_file: RunFile) -> int | None:
    """Size of a run file's stored bytes, or None if it is missing."""
    path = settings.data_dir / run_file.storage_key
    return path.stat().st_size if path.exists() else None


def count_facts(db: Session, run_id: int) -> int:
    """Number of fact rows ingested for a run."""
    return db.scalar(
        select(func.count()).select_from(Fact).where(Fact.run_id == run_id)
    )


def list_facts(db: Session, run_id: int) -> list[Fact]:
    """The ingested facts for a run (input-data view)."""
    return facts.list_facts(db, run_id, limit=1_000_000)


def read_run_file_path(settings: Settings, run_file: RunFile) -> Path:
    path = settings.data_dir / run_file.storage_key
    if not path.exists():
        raise ArtifactUnavailableError(
            f"the stored {run_file.role.value} file ({run_file.filename}) is no "
            "longer present at the storage root; re-run to regenerate it"
        )
    return path
