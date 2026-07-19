"""HTTP routes for workflows — thin: parse, call service, shape response.

The demo surface: list suites, create/execute runs, attach inputs, inspect a
run, download outputs, and browse run history.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.facts.schemas import FactIngestSummary, RunFileOut
from app.taxonomy.schemas import TemplateInfo
from app.validation.schemas import FindingOut
from app.workflows import service, version_selection
from app.workflows.models import RunStatus
from app.workflows.schemas import (
    CategoryOut,
    EntityOut,
    EntityWorkflowConfigOut,
    EntityWorkflowConfigWrite,
    EntityWrite,
    FactRowOut,
    ModuleVersionOptions,
    OutputFormatWrite,
    ReexecuteRequest,
    RegisterRowOut,
    RegulatorFormatOut,
    ReleaseProvisionsSummary,
    RunCreate,
    RunDetailOut,
    RunOut,
    RunSummaryOut,
    SuiteSummaryOut,
    VerdictOut,
    WorkflowConfigOut,
    WorkflowFormatOut,
    WorkflowSettingsUpdate,
)

router = APIRouter()


def _run_summary(run) -> RunSummaryOut | None:
    return RunSummaryOut.model_validate(run) if run is not None else None


@router.get("/configs", response_model=list[WorkflowConfigOut])
def list_workflows(
    category: str | None = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
) -> list[WorkflowConfigOut]:
    return [
        WorkflowConfigOut.model_validate(w)
        for w in service.list_workflows(
            db, active_only=not include_inactive, category=category
        )
    ]


@router.patch("/configs/{workflow_id}", response_model=WorkflowConfigOut)
def update_workflow_settings(
    workflow_id: int,
    body: WorkflowSettingsUpdate,
    db: Session = Depends(get_db),
) -> WorkflowConfigOut:
    """Settings: set a workflow's category and active flag (persists live)."""
    wf = service.update_workflow_settings(
        db, workflow_id, category=body.category, is_active=body.is_active
    )
    return WorkflowConfigOut.model_validate(wf)


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)) -> list[CategoryOut]:
    """Reporting landing tiles: per-category active count + latest activity."""
    return [
        CategoryOut(
            category=s["category"],
            active_count=s["active_count"],
            last_run=_run_summary(s["last_run"]),
        )
        for s in service.category_summaries(db)
    ]


@router.get(
    "/categories/{category}/suites", response_model=list[SuiteSummaryOut]
)
def list_category_suites(
    category: str, db: Session = Depends(get_db)
) -> list[SuiteSummaryOut]:
    """Active suites in a category, each with its most recent run."""
    out: list[SuiteSummaryOut] = []
    for s in service.suite_summaries(db, category):
        wf = s["workflow"]
        out.append(
            SuiteSummaryOut(
                id=wf.id,
                name=wf.name,
                framework_code=wf.framework_code,
                module_code=wf.module_code,
                category=wf.category,
                is_active=wf.is_active,
                last_run=_run_summary(s["last_run"]),
            )
        )
    return out


@router.get("/configs/{workflow_id}/templates", response_model=list[TemplateInfo])
def workflow_templates(
    workflow_id: int, snapshot_id: int, db: Session = Depends(get_db)
) -> list[TemplateInfo]:
    """Templates composing the workflow's module in a release (for config UI)."""
    return service.list_module_templates(db, workflow_id, snapshot_id)


@router.get(
    "/configs/{workflow_id}/module-versions",
    response_model=ModuleVersionOptions,
)
def module_versions(
    workflow_id: int, db: Session = Depends(get_db)
) -> ModuleVersionOptions:
    """The distinct taxonomy versions this suite's module is available at, across
    all ready releases — the submission workspace's version selector."""
    return version_selection.list_module_versions(db, workflow_id)


@router.get(
    "/releases/{snapshot_id}/provisions",
    response_model=ReleaseProvisionsSummary,
)
def release_provisions(
    snapshot_id: int, db: Session = Depends(get_db)
) -> ReleaseProvisionsSummary:
    """What a release provides for each enabled suite, and whether it is new —
    the ingestion summary shown after a release finishes ingesting."""
    return version_selection.release_provisions_summary(db, snapshot_id)


@router.get("/entities", response_model=list[EntityOut])
def list_entities(db: Session = Depends(get_db)) -> list[EntityOut]:
    return [EntityOut.model_validate(e) for e in service.list_entities(db)]


@router.post("/entities", response_model=EntityOut, status_code=201)
def create_entity(body: EntityWrite, db: Session = Depends(get_db)) -> EntityOut:
    entity = service.create_entity(
        db,
        name=body.name,
        lei=body.lei,
        country=body.country,
        default_scope=body.default_scope,
    )
    return EntityOut.model_validate(entity)


@router.get("/entities/{entity_id}", response_model=EntityOut)
def get_entity(entity_id: int, db: Session = Depends(get_db)) -> EntityOut:
    return EntityOut.model_validate(service.get_entity(db, entity_id))


@router.put("/entities/{entity_id}", response_model=EntityOut)
def update_entity(
    entity_id: int, body: EntityWrite, db: Session = Depends(get_db)
) -> EntityOut:
    entity = service.update_entity(
        db,
        entity_id,
        name=body.name,
        lei=body.lei,
        country=body.country,
        default_scope=body.default_scope,
    )
    return EntityOut.model_validate(entity)


@router.delete("/entities/{entity_id}", status_code=204)
def delete_entity(entity_id: int, db: Session = Depends(get_db)) -> None:
    """Delete an entity (live reference data). Runs keep their frozen values."""
    service.delete_entity(db, entity_id)


@router.get(
    "/entities/{entity_id}/configs/{workflow_id}",
    response_model=EntityWorkflowConfigOut,
)
def get_entity_workflow_config(
    entity_id: int, workflow_id: int, db: Session = Depends(get_db)
) -> EntityWorkflowConfigOut:
    service.get_entity(db, entity_id)  # 404 if unknown
    service.get_workflow(db, workflow_id)
    config = service.get_entity_workflow_config(db, entity_id, workflow_id)
    if config is None:
        return EntityWorkflowConfigOut(
            entity_id=entity_id,
            workflow_id=workflow_id,
            indicator_declarations={},
            base_currency=None,
            decimals=None,
        )
    return EntityWorkflowConfigOut.model_validate(config)


@router.put(
    "/entities/{entity_id}/configs/{workflow_id}",
    response_model=EntityWorkflowConfigOut,
)
def update_entity_workflow_config(
    entity_id: int,
    workflow_id: int,
    body: EntityWorkflowConfigWrite,
    db: Session = Depends(get_db),
) -> EntityWorkflowConfigOut:
    config = service.upsert_entity_workflow_config(
        db,
        entity_id=entity_id,
        workflow_id=workflow_id,
        indicator_declarations=body.indicator_declarations,
        base_currency=body.base_currency,
        decimals=body.decimals,
    )
    return EntityWorkflowConfigOut.model_validate(config)


# --- output-format configuration -------------------------------------------


@router.get(
    "/regulators/{regulator_id}/format", response_model=RegulatorFormatOut
)
def get_regulator_format(
    regulator_id: int, db: Session = Depends(get_db)
) -> RegulatorFormatOut:
    fmt = service.regulator_format(db, regulator_id)
    return RegulatorFormatOut(regulator_id=regulator_id, output_format=fmt)


@router.put(
    "/regulators/{regulator_id}/format", response_model=RegulatorFormatOut
)
def set_regulator_format(
    regulator_id: int,
    body: OutputFormatWrite,
    db: Session = Depends(get_db),
) -> RegulatorFormatOut:
    fmt = service.set_regulator_format_default(
        db, regulator_id=regulator_id, output_format=body.output_format
    )
    return RegulatorFormatOut(regulator_id=regulator_id, output_format=fmt)


def _workflow_format_out(
    regulator_id: int, workflow_id: int, db: Session
) -> WorkflowFormatOut:
    effective, overridden, default = service.workflow_format(
        db, regulator_id, workflow_id
    )
    return WorkflowFormatOut(
        regulator_id=regulator_id,
        workflow_id=workflow_id,
        output_format=effective,
        overridden=overridden,
        regulator_default=default,
    )


@router.get(
    "/regulators/{regulator_id}/configs/{workflow_id}/format",
    response_model=WorkflowFormatOut,
)
def get_workflow_format(
    regulator_id: int, workflow_id: int, db: Session = Depends(get_db)
) -> WorkflowFormatOut:
    return _workflow_format_out(regulator_id, workflow_id, db)


@router.put(
    "/regulators/{regulator_id}/configs/{workflow_id}/format",
    response_model=WorkflowFormatOut,
)
def set_workflow_format(
    regulator_id: int,
    workflow_id: int,
    body: OutputFormatWrite,
    db: Session = Depends(get_db),
) -> WorkflowFormatOut:
    service.set_workflow_format_override(
        db,
        regulator_id=regulator_id,
        workflow_id=workflow_id,
        output_format=body.output_format,
    )
    return _workflow_format_out(regulator_id, workflow_id, db)


@router.delete(
    "/regulators/{regulator_id}/configs/{workflow_id}/format",
    response_model=WorkflowFormatOut,
)
def clear_workflow_format(
    regulator_id: int, workflow_id: int, db: Session = Depends(get_db)
) -> WorkflowFormatOut:
    """Remove the per-workflow override so the regulator default applies."""
    service.workflow_format(db, regulator_id, workflow_id)  # 404 checks
    service.clear_workflow_format_override(
        db, regulator_id=regulator_id, workflow_id=workflow_id
    )
    return _workflow_format_out(regulator_id, workflow_id, db)


@router.get("/configs/{workflow_id}/runs", response_model=list[RunOut])
def run_history(
    workflow_id: int, db: Session = Depends(get_db)
) -> list[RunOut]:
    service.get_workflow(db, workflow_id)  # 404 if unknown
    return [RunOut.model_validate(r) for r in service.list_runs(db, workflow_id)]


@router.post("/runs", response_model=RunOut, status_code=201)
def create_run(body: RunCreate, db: Session = Depends(get_db)) -> RunOut:
    run = service.create_run(
        db,
        workflow_id=body.workflow_id,
        snapshot_id=body.snapshot_id,
        reference_date=body.reference_date,
        entity_id=body.entity_id,
        snapshot_key=body.snapshot_key,
        adjusted_key=body.adjusted_key,
        version_key=body.version_key,
        base_currency=body.base_currency,
        decimals=body.decimals,
        release_id=body.release_id,
    )
    return RunOut.model_validate(run)


@router.post("/runs/{run_id}/reexecute", response_model=RunOut, status_code=201)
def reexecute_run(
    run_id: int,
    body: ReexecuteRequest | None = None,
    db: Session = Depends(get_db),
) -> RunOut:
    """Create a fresh execution of an existing instance (re-execute / resubmit).

    Returns a new run in ``created`` status carrying the source run's instance
    identity; the caller attaches a fact file and executes it. If the entity or
    release has changed since the last execution, responds 409
    ``dependency_changed`` with the list of changes; the client retries with a
    replacement (``entity_id`` / ``release_snapshot_id``) or, for a still-usable
    change, ``acknowledge_changes: true``.
    """
    body = body or ReexecuteRequest()
    run = service.reexecute_run(
        db,
        run_id,
        entity_id=body.entity_id,
        release_snapshot_id=body.release_snapshot_id,
        acknowledge_changes=body.acknowledge_changes,
    )
    return RunOut.model_validate(run)


@router.delete("/runs/{run_id}", status_code=204)
def delete_run(run_id: int, db: Session = Depends(get_db)) -> None:
    """Delete an execution and its artifacts. Other executions are untouched."""
    service.delete_run(db, run_id, settings=get_settings())


@router.get("/runs/{run_id}", response_model=RunDetailOut)
def run_detail(run_id: int, db: Session = Depends(get_db)) -> RunDetailOut:
    run = service.get_run(db, run_id)
    files = service.run_files(db, run_id)
    findings = service.list_findings(db, run_id)
    settings = get_settings()

    def _file_out(f) -> RunFileOut:
        out = RunFileOut.model_validate(f)
        # Reconcile with disk so a missing artifact is a clear state, not a 404
        # on click (mirrors the snapshot artifact reconciliation).
        out.available = service.run_file_available(settings, f)
        out.size_bytes = service.run_file_size(settings, f)
        return out

    register = [
        RegisterRowOut(
            id=r.id, rule=r.rule, source=r.source, template=r.template,
            data_evaluated=r.data_evaluated, result=r.result, detail=r.detail,
            rule_text=r.rule_text, description=r.description, severity=r.severity,
            blocking=r.blocking, evaluations=r.evaluations,
            satisfied=r.satisfied, not_satisfied=r.not_satisfied,
        )
        for r in service.build_run_register(db, run, findings)
    ]
    return RunDetailOut(
        run=RunOut.model_validate(run),
        files=[_file_out(f) for f in files],
        findings=[FindingOut.model_validate(f) for f in findings],
        fact_count=service.count_facts(db, run_id),
        filing_indicators=run.filing_indicators,
        rule_register=register,
        formula_summary=run.formula_summary,
        verdict=VerdictOut(**service.run_verdict(run, findings, run.formula_summary)),
    )


@router.get("/runs/{run_id}/facts", response_model=list[FactRowOut])
def run_facts(run_id: int, db: Session = Depends(get_db)) -> list[FactRowOut]:
    """The ingested facts for a run (input-data view)."""
    service.get_run(db, run_id)  # 404 if unknown
    return [
        FactRowOut.model_validate(f)
        for f in service.list_facts(db, run_id)
    ]


@router.post(
    "/runs/{run_id}/fact-file",
    response_model=FactIngestSummary,
    status_code=201,
)
async def attach_fact_file(
    run_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> FactIngestSummary:
    data = await file.read()
    return service.attach_fact_file(
        db, run_id=run_id, filename=file.filename or "facts.xlsx", data=data
    )


# The indicators/parameters upload override is intentionally not exposed on the
# run-creation API surface. The parser + service (attach_indicators_params_file)
# and execute-time override path remain in the codebase for later use.


@router.post("/runs/{run_id}/execute", response_model=RunOut)
def execute_run(
    run_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> RunOut:
    run = service.execute_run(db, run_id)
    # Structural is done; if formula validation was queued, run it off-request.
    if run.status is RunStatus.formula_validation_running:
        background.add_task(service.run_formula_validation_task, run.id)
    return RunOut.model_validate(run)


@router.get("/run-files/{run_file_id}/download")
def download_run_file(
    run_file_id: int, db: Session = Depends(get_db)
) -> FileResponse:
    run_file = service.get_run_file(db, run_file_id)
    path = service.read_run_file_path(get_settings(), run_file)
    return FileResponse(
        path, filename=run_file.filename, media_type="application/octet-stream"
    )