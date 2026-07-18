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
from app.facts.schemas import (
    FactIngestSummary,
    IndicatorsParamsIngestSummary,
    RunFileOut,
)
from app.taxonomy.schemas import TemplateInfo
from app.validation.schemas import FindingOut
from app.workflows import service
from app.workflows.models import RunStatus
from app.workflows.schemas import (
    EntityOut,
    EntityWorkflowConfigOut,
    EntityWorkflowConfigWrite,
    EntityWrite,
    RunCreate,
    RunDetailOut,
    RunOut,
    WorkflowConfigOut,
)

router = APIRouter()


@router.get("/configs", response_model=list[WorkflowConfigOut])
def list_workflows(db: Session = Depends(get_db)) -> list[WorkflowConfigOut]:
    return [
        WorkflowConfigOut.model_validate(w) for w in service.list_workflows(db)
    ]


@router.get("/configs/{workflow_id}/templates", response_model=list[TemplateInfo])
def workflow_templates(
    workflow_id: int, snapshot_id: int, db: Session = Depends(get_db)
) -> list[TemplateInfo]:
    """Templates composing the workflow's module in a release (for config UI)."""
    return service.list_module_templates(db, workflow_id, snapshot_id)


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
        scope=body.scope,
        base_currency=body.base_currency,
        decimals=body.decimals,
        release_id=body.release_id,
    )
    return RunOut.model_validate(run)


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
        return out

    return RunDetailOut(
        run=RunOut.model_validate(run),
        files=[_file_out(f) for f in files],
        findings=[FindingOut.model_validate(f) for f in findings],
    )


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


@router.post(
    "/runs/{run_id}/indicators-params-file",
    response_model=IndicatorsParamsIngestSummary,
    status_code=201,
)
async def attach_indicators_params_file(
    run_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> IndicatorsParamsIngestSummary:
    data = await file.read()
    return service.attach_indicators_params_file(
        db,
        run_id=run_id,
        filename=file.filename or "indicators_params.xlsx",
        data=data,
    )


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