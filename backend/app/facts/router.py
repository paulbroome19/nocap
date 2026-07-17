"""HTTP routes for the facts stage — thin: parse, call service, shape response.

Attach the two input files to a run context and inspect what was ingested. The
``Run`` itself lands in the workflows stage; here ``run_id`` is taken as a path
parameter (build-to-interface). The template-code normaliser is provided via
``get_template_normalizer`` — a dependency the app composition root wires to the
taxonomy contract, so this stage never imports another stage.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.facts import service
from app.facts.parsers import TemplateNormalizer
from app.facts.schemas import (
    FactIngestSummary,
    FactOut,
    IndicatorsParamsIngestSummary,
    RunFileOut,
)

router = APIRouter()


def get_template_normalizer() -> TemplateNormalizer:
    """Interface seam — overridden at the composition root (see app.main)."""
    raise NotImplementedError(
        "template normaliser not wired; the app composition root must override "
        "get_template_normalizer"
    )


@router.post(
    "/runs/{run_id}/fact-file",
    response_model=FactIngestSummary,
    status_code=201,
)
async def attach_fact_file(
    run_id: int,
    entity: str = Form(...),
    reference_date: date = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    normalize: TemplateNormalizer = Depends(get_template_normalizer),
) -> FactIngestSummary:
    data = await file.read()
    return service.ingest_fact_file(
        db,
        run_id=run_id,
        entity=entity,
        reference_date=reference_date,
        filename=file.filename or "facts.xlsx",
        data=data,
        normalize=normalize,
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
    normalize: TemplateNormalizer = Depends(get_template_normalizer),
) -> IndicatorsParamsIngestSummary:
    data = await file.read()
    return service.ingest_indicators_params_file(
        db,
        run_id=run_id,
        filename=file.filename or "indicators_params.xlsx",
        data=data,
        normalize=normalize,
    )


@router.get("/runs/{run_id}/files", response_model=list[RunFileOut])
def list_run_files(run_id: int, db: Session = Depends(get_db)) -> list[RunFileOut]:
    return [RunFileOut.model_validate(f) for f in service.list_run_files(db, run_id)]


@router.get("/runs/{run_id}/facts", response_model=list[FactOut])
def list_facts(run_id: int, db: Session = Depends(get_db)) -> list[FactOut]:
    return [FactOut.model_validate(f) for f in service.list_facts(db, run_id)]
