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


def _run_validation(db: Session, run: Run, package: GeneratedPackage) -> None:
    """SEAM for the validation stage — currently a pass-through.

    The validation stage will run structural checks here (every (report,row,col)
    resolves; values parse under the datatype; filing indicators consistent;
    package layout conforms), persist a ``validation_report`` RunFile, and fail
    the run on hard errors. For now generation flows straight to ``generated``.
    """
    return None


def execute_run(
    db: Session, run_id: int, *, settings: Settings | None = None
) -> Run:
    settings = settings or get_settings()
    run = get_run(db, run_id)
    if run.status is RunStatus.running:
        raise ValidationError(f"run id={run_id} is already running")

    files = facts.list_run_files(db, run.id)
    if not any(f.role is RunFileRole.fact_input for f in files):
        raise ValidationError("no fact file attached to this run")
    ind_files = [f for f in files if f.role is RunFileRole.indicators_params]
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

        with taxonomy.open_lookup(snapshot, settings=settings) as lk:
            meta = lk.module_metadata(wf.module_code, release_id=run.release_id)
            if meta is None:
                raise ValidationError(
                    f"module {wf.module_code} is not in the bound snapshot"
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
            package = generation.build_package(
                fact_inputs,
                metadata,
                resolve=lambda t, r, c: lk.resolve(
                    t, r, c, release_id=run.release_id
                ),
            )

        # Validation seam (pass-through in v1) — see _run_validation.
        _run_validation(db, run, package)

        def _store(session, rid, filename, data):
            return facts.store_run_file(
                session,
                run_id=rid,
                role=RunFileRole.package_output,
                filename=filename,
                data=data,
                settings=settings,
            )

        generation.store_package(db, run_id=run.id, package=package, store=_store)
        run.status = RunStatus.generated
        db.commit()
        logger.info(
            "run id=%s generated %s (%d facts)",
            run.id,
            package.filename,
            package.fact_count,
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
