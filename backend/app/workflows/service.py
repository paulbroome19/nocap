"""Orchestration: the only place that composes the pipeline stages.

Run lifecycle: create → attach fact + indicators/params files (facts stage) →
execute (resolve facts against the bound snapshot+release+module via taxonomy →
build the package via generation → persist outputs). ``workflows`` is the sole
package allowed to import other stages.

The package's creation timestamp is derived deterministically from the run id +
reference date (never ``now()``), so a run's package is reproducible.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import SessionLocal
from app.core.errors import (
    ArtifactUnavailableError,
    ConflictError,
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
from app.generation.schemas import (
    FactInput,
    FilingIndicatorSpec,
    PackageMetadata,
)
from app.taxonomy import service as taxonomy
from app.taxonomy.models import SnapshotStatus
from app.taxonomy.service import normalize_template_code
from app.validation import service as validation
from app.validation.arelle_adapter import ArelleFormulaValidator
from app.validation.models import Severity, ValidationFinding, ValidationPhase
from app.validation.schemas import Finding
from app.workflows.models import (
    WORKFLOW_CATEGORIES,
    Entity,
    EntityWorkflowConfig,
    Run,
    RunStatus,
    WorkflowConfig,
)

logger = logging.getLogger(__name__)

_ATTACHABLE = {RunStatus.created, RunStatus.files_attached}

# Filing-indicator declarations (per template, in an EntityWorkflowConfig).
DECLARATION_AUTO = "auto"  # report iff the template has resolvable facts (default)
DECLARATION_TRUE = "true"  # force a positive indicator, even with no facts
DECLARATION_FALSE = "false"  # declare not-filed; force negative + exclude facts
_VALID_DECLARATIONS = {DECLARATION_AUTO, DECLARATION_TRUE, DECLARATION_FALSE}


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
    """Normalise a template→declaration map: canonical codes, drop Auto/invalid.

    Only non-Auto declarations are stored (Auto is the absence of an entry), so
    the map stays compact and templates default to Auto.
    """
    out: dict[str, str] = {}
    for code, decl in (declarations or {}).items():
        value = str(decl).strip().lower()
        if value not in _VALID_DECLARATIONS or value == DECLARATION_AUTO:
            continue
        try:
            out[_normalize(code)] = value
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


def list_module_templates(
    db: Session, workflow_id: int, snapshot_id: int
) -> list:
    """Templates composing a workflow's module in a release (for the config UI).

    Returns the taxonomy ``TemplateInfo`` list (code + name). Requires a ready
    release so the module can be resolved.
    """
    wf = get_workflow(db, workflow_id)
    snapshot = taxonomy.get_snapshot(db, snapshot_id)
    with taxonomy.open_lookup(snapshot) as lk:
        return lk.list_templates(wf.module_code)


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
        if lk.module_metadata(wf.module_code, release_id=rid) is None:
            raise ValidationError(
                f"module {wf.module_code} is not in snapshot id={snapshot_id} "
                f"at release {rid}"
            )

    run = Run(
        workflow_id=wf.id,
        snapshot_id=snapshot.id,
        release_id=rid,
        reference_date=reference_date,
        entity_id=entity.id,
        entity_lei=_validate_lei(entity.lei),
        entity_scope=run_scope,
        country=entity.country.upper(),
        snapshot_key=_key(snapshot_key),
        adjusted_key=_key(adjusted_key),
        version_key=_key(version_key),
        base_currency=currency,
        decimals=decimals if decimals is not None else -3,
        status=RunStatus.created,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    logger.info(
        "created run id=%s workflow=%s entity=%s", run.id, wf.module_code,
        entity.lei, extra={"run_id": run.id},
    )
    return run


def get_run(db: Session, run_id: int) -> Run:
    run = db.get(Run, run_id)
    if run is None:
        raise NotFoundError(f"run id={run_id} not found")
    return run


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

    Auto (default): reported iff it has closed, resolvable facts. True: forced
    positive. False: forced negative.
    """
    decl = declarations.get(template, DECLARATION_AUTO)
    if decl == DECLARATION_TRUE:
        return True
    if decl == DECLARATION_FALSE:
        return False
    return template in closed_with_facts


def _derive_indicators_params(
    run: Run,
    module_templates: set[str],
    closed_with_facts: set[str],
    declarations: dict[str, str],
) -> IndicatorsParams:
    """Derive indicators & parameters in-system from the run + its facts.

    Filing indicators: every module template, reported per its declaration
    (Auto/True/False — see ``_resolve_declaration``). Parameters: entity +
    reference date + base currency + decimals from the run.
    """
    return IndicatorsParams(
        filing_indicators=[
            FilingIndicator(
                template_code=template,
                reported=_resolve_declaration(
                    template, declarations, closed_with_facts
                ),
            )
            for template in sorted(module_templates)
        ],
        entity_lei=run.entity_lei,
        reference_date=run.reference_date,
        base_currency=run.base_currency,
        decimals=run.decimals,
    )


def _load_declarations(db: Session, run: Run) -> dict[str, str]:
    """The entity+workflow filing-indicator declarations for a run (canonical)."""
    if run.entity_id is None:
        return {}
    ewc = get_entity_workflow_config(db, run.entity_id, run.workflow_id)
    return dict(ewc.indicator_declarations) if ewc else {}


def _not_filed_findings(
    fact_rows, module_templates: set[str], declarations: dict[str, str]
) -> tuple[set[str], list[Finding]]:
    """Templates declared not-filed, and a warning per one that has facts.

    Returns ``(excluded_templates, findings)``. Any facts for an excluded
    template are dropped from the package; the warning records how many.
    """
    excluded = {
        t for t in module_templates if declarations.get(t) == DECLARATION_FALSE
    }
    findings: list[Finding] = []
    for template in sorted(excluded):
        n = sum(1 for f in fact_rows if f.template_code == template)
        if n:
            findings.append(
                Finding(
                    severity=Severity.warning,
                    phase=ValidationPhase.pre_generation,
                    code="TEMPLATE_DECLARED_NOT_FILED",
                    message=f"template {template} declared not-filed; "
                    f"{n} facts excluded",
                    template_code=template,
                )
            )
    return excluded, findings


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


def _report_header(run: Run, wf: WorkflowConfig, package_filename: str) -> list[str]:
    return [
        f"Run #{run.id}  •  {wf.name}  [{wf.module_code}]",
        f"Entity: {run.entity_lei}.{run.entity_scope}   "
        f"Reference date: {run.reference_date}",
        f"Snapshot: {run.snapshot_id} (release {run.release_id})   "
        f"Package: {package_filename}",
    ]


def _append_findings(db: Session, run_id: int, findings: list[Finding]) -> None:
    db.add_all(
        ValidationFinding(run_id=run_id, **f.model_dump()) for f in findings
    )
    db.commit()


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
    report = validation.build_report_text(
        header_lines=_report_header(run, wf, package_filename), findings=findings
    )
    facts.upsert_run_file(
        db,
        run_id=run.id,
        role=RunFileRole.validation_report,
        filename=f"validation_report_run{run.id}.txt",
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
                f for f in fact_rows if f.template_code not in excluded_templates
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

            # Indicators & parameters: uploaded override, else derived in-system.
            if ind_files:
                params = _load_params(settings, ind_files[-1])
            else:
                params = _derive_indicators_params(
                    run, module_templates, closed_with_facts, declarations
                )

            # Persist the filing-indicator outcomes for traceability — which
            # templates report true/false and why (a declaration, or Auto).
            run.filing_indicators = [
                {
                    "template_code": fi.template_code,
                    "reported": fi.reported,
                    "source": (
                        "declared"
                        if ind_files
                        or declarations.get(fi.template_code)
                        in (DECLARATION_TRUE, DECLARATION_FALSE)
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
            package = generation.build_package(
                generatable, metadata, resolve=resolve, strict=False
            )

        # Phase 2 — post-generation checks on the built package.
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
        validator = ArelleFormulaValidator(cache_dir=settings.data_dir / "cache")
        findings = validator.validate(package_path, taxo)  # never raises

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


def read_run_file_path(settings: Settings, run_file: RunFile) -> Path:
    path = settings.data_dir / run_file.storage_key
    if not path.exists():
        raise ArtifactUnavailableError(
            f"the stored {run_file.role.value} file ({run_file.filename}) is no "
            "longer present at the storage root; re-run to regenerate it"
        )
    return path
