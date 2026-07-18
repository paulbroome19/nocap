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

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import NotFoundError, ValidationError
from app.facts import service as facts
from app.facts.models import RunFile, RunFileRole
from app.facts.parsers import default_indicators_params_parser
from app.facts.schemas import (
    FactIngestSummary,
    IndicatorsParams,
    IndicatorsParamsIngestSummary,
)
from app.generation import service as generation
from app.generation.schemas import (
    FactInput,
    FilingIndicatorSpec,
    GeneratedPackage,
    PackageMetadata,
)
from app.taxonomy import service as taxonomy
from app.taxonomy.models import SnapshotStatus
from app.taxonomy.service import normalize_template_code
from app.validation import service as validation
from app.validation.models import Severity, ValidationFinding, ValidationPhase
from app.validation.schemas import Finding
from app.workflows.models import Run, RunStatus, WorkflowConfig

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
    db: Session, *, active_only: bool = True
) -> list[WorkflowConfig]:
    stmt = select(WorkflowConfig).order_by(WorkflowConfig.name)
    if active_only:
        stmt = stmt.where(WorkflowConfig.active.is_(True))
    return list(db.scalars(stmt))


def get_workflow(db: Session, workflow_id: int) -> WorkflowConfig:
    wf = db.get(WorkflowConfig, workflow_id)
    if wf is None:
        raise NotFoundError(f"workflow id={workflow_id} not found")
    return wf


# --- run lifecycle ---------------------------------------------------------


def create_run(
    db: Session,
    *,
    workflow_id: int,
    snapshot_id: int,
    reference_date: date,
    entity_lei: str,
    entity_scope: str = "CON",
    release_id: int | None = None,
    country: str | None = None,
    settings: Settings | None = None,
) -> Run:
    settings = settings or get_settings()
    wf = get_workflow(db, workflow_id)
    if not wf.active:
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

    scope = entity_scope.strip().upper()
    if scope not in {"IND", "CON"}:
        raise ValidationError("entity_scope must be IND or CON")
    lei = _validate_lei(entity_lei)

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
        entity_lei=lei,
        entity_scope=scope,
        country=(country or settings.default_country).upper(),
        status=RunStatus.created,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    logger.info(
        "created run id=%s workflow=%s", run.id, wf.module_code,
        extra={"run_id": run.id},
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


def _report_header(
    run: Run, wf: WorkflowConfig, package: GeneratedPackage
) -> list[str]:
    return [
        f"Run #{run.id}  •  {wf.name}  [{wf.module_code}]",
        f"Entity: {run.entity_lei}.{run.entity_scope}   "
        f"Reference date: {run.reference_date}",
        f"Snapshot: {run.snapshot_id} (release {run.release_id})   "
        f"Package: {package.filename}",
    ]


def execute_run(
    db: Session, run_id: int, *, settings: Settings | None = None
) -> Run:
    settings = settings or get_settings()
    run = get_run(db, run_id)
    if run.status is RunStatus.running:
        raise ValidationError(f"run id={run_id} is already running")

    files = facts.list_run_files(db, run.id)
    fact_files = [f for f in files if f.role is RunFileRole.fact_input]
    ind_files = [f for f in files if f.role is RunFileRole.indicators_params]
    if not fact_files:
        raise ValidationError("no fact file attached to this run")
    if not ind_files:
        raise ValidationError(
            "no indicators/parameters file attached to this run"
        )

    run.status = RunStatus.running
    run.error = None
    run.failure_details = None
    db.commit()
    logger.info("executing run id=%s", run.id, extra={"run_id": run.id})

    try:
        wf = get_workflow(db, run.workflow_id)
        snapshot = taxonomy.get_snapshot(db, run.snapshot_id)
        params = _load_params(settings, ind_files[-1])
        fact_rows = facts.list_facts(db, run.id, limit=1_000_000)
        fact_inputs = [
            FactInput(
                template_code=f.template_code,
                row_code=f.row_code,
                column_code=f.column_code,
                value=f.value,
            )
            for f in fact_rows
        ]
        findings: list[Finding] = []

        with taxonomy.open_lookup(snapshot, settings=settings) as lk:
            meta = lk.module_metadata(wf.module_code, release_id=run.release_id)
            if meta is None:
                raise ValidationError(
                    f"module {wf.module_code} is not in the bound snapshot"
                )
            module_templates = {
                t.code
                for t in lk.list_templates(wf.module_code, release_id=run.release_id)
            }

            def resolve(t, r, c):
                return lk.resolve(t, r, c, release_id=run.release_id)

            # Phase 1 — pre-generation checks on the facts.
            findings += _safe_validate(
                "facts",
                lambda: validation.validate_facts(
                    facts=fact_rows,
                    resolve=resolve,
                    module_templates=module_templates,
                    filing_indicators=params.filing_indicators,
                    fact_file_name=fact_files[-1].filename,
                    entity_id=run.entity_lei,
                    ref_period=run.reference_date,
                ),
            )
            datatypes_present = {
                res.datatype_code
                for f in fact_rows
                if (res := resolve(f.template_code, f.row_code, f.column_code))
            }

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
            # Lenient build so a package is always produced for inspection; the
            # unresolved/duplicate facts are reported as findings above.
            package = generation.build_package(
                fact_inputs, metadata, resolve=resolve, strict=False
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

        # Persist findings, the package (always), and the validation report.
        _persist_findings(db, run.id, findings)
        generation.store_package(db, run_id=run.id, package=package, store=_store)
        report = validation.build_report_text(
            header_lines=_report_header(run, wf, package), findings=findings
        )
        _store(
            db, run.id, f"validation_report_run{run.id}.txt",
            report.encode("utf-8"), role=RunFileRole.validation_report,
        )

        has_errors = any(f.severity is Severity.error for f in findings)
        run.status = (
            RunStatus.failed_validation if has_errors else RunStatus.generated
        )
        db.commit()
        logger.info(
            "run id=%s %s (%d findings, %d errors)",
            run.id,
            run.status.value,
            len(findings),
            sum(f.severity is Severity.error for f in findings),
            extra={"run_id": run.id},
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


# --- run files -------------------------------------------------------------


def run_files(db: Session, run_id: int) -> list[RunFile]:
    get_run(db, run_id)  # 404 if the run doesn't exist
    return facts.list_run_files(db, run_id)


def get_run_file(db: Session, run_file_id: int) -> RunFile:
    run_file = db.get(RunFile, run_file_id)
    if run_file is None:
        raise NotFoundError(f"run file id={run_file_id} not found")
    return run_file


def read_run_file_path(settings: Settings, run_file: RunFile) -> Path:
    path = settings.data_dir / run_file.storage_key
    if not path.exists():
        raise NotFoundError(
            f"stored bytes for run file id={run_file.id} are missing"
        )
    return path
