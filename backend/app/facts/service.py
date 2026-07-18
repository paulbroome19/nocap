"""Business logic for the facts stage.

Ingest the two run inputs (fact XLSX; indicators/parameters file), storing each
byte-for-byte as a ``RunFile`` and appending ``Fact`` events. Validation here is
**shape only** (parseable, non-empty, well-formed codes) — datapoint resolution
and datatype checks are the validation stage's job.

Per the dependency rules this imports only from ``app.core``. The template-code
normaliser is injected (``TemplateNormalizer``); ``workflows`` / the app
composition root supplies the taxonomy contract's implementation.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import FileRejectedError, ValidationError
from app.facts.models import Fact, RunFile, RunFileRole
from app.facts.parsers import (
    IndicatorsParamsParser,
    TemplateNormalizer,
    default_indicators_params_parser,
    parse_fact_xlsx,
)
from app.facts.schemas import (
    FactIngestSummary,
    IndicatorsParamsIngestSummary,
    RunFileOut,
)

logger = logging.getLogger(__name__)


def compute_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _run_dir(settings: Settings, run_id: int) -> Path:
    return settings.data_dir / "runs" / str(run_id)


def _validate_lei(entity: str) -> str:
    entity = entity.strip()
    if len(entity) != 20 or not entity.isalnum():
        raise ValidationError(
            f"malformed entity LEI {entity!r} (expected 20 alphanumeric chars)"
        )
    return entity.upper()


def store_run_file(
    db: Session,
    *,
    run_id: int,
    role: RunFileRole,
    filename: str,
    data: bytes,
    settings: Settings,
) -> RunFile:
    """Persist an uploaded file to disk and register a ``RunFile`` row."""
    directory = _run_dir(settings, run_id) / role.value
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_bytes(data)

    run_file = RunFile(
        run_id=run_id,
        role=role,
        filename=filename,
        storage_key=str(path.relative_to(settings.data_dir).as_posix()),
        checksum=compute_checksum(data),
    )
    db.add(run_file)
    db.flush()
    return run_file


def ingest_fact_file(
    db: Session,
    *,
    run_id: int,
    entity: str,
    reference_date: date,
    filename: str,
    data: bytes,
    normalize: TemplateNormalizer,
    settings: Settings | None = None,
) -> FactIngestSummary:
    """Parse + persist a fact XLSX as append-only facts for a run.

    Rejects the whole file (nothing persisted) if any row fails shape checks.
    """
    settings = settings or get_settings()
    entity = _validate_lei(entity)

    result = parse_fact_xlsx(data, normalize=normalize)
    if result.errors:
        raise FileRejectedError(
            "fact file rejected", details=[e.model_dump() for e in result.errors]
        )
    if not result.facts:
        raise FileRejectedError(
            "fact file rejected", details=[{"message": "no fact rows found"}]
        )

    run_file = store_run_file(
        db,
        run_id=run_id,
        role=RunFileRole.fact_input,
        filename=filename,
        data=data,
        settings=settings,
    )
    db.add_all(
        Fact(
            run_id=run_id,
            template_code=f.template_code,
            row_code=f.row_code,
            column_code=f.column_code,
            value=f.value,
            entity=entity,
            reference_date=reference_date,
            source_sheet=f.source_sheet,
            source_row=f.source_row,
        )
        for f in result.facts
    )
    db.commit()
    db.refresh(run_file)
    logger.info(
        "ingested %d facts for run=%s from %s", len(result.facts), run_id, filename
    )
    return FactIngestSummary(
        run_file=RunFileOut.model_validate(run_file),
        fact_count=len(result.facts),
    )


def ingest_indicators_params_file(
    db: Session,
    *,
    run_id: int,
    filename: str,
    data: bytes,
    normalize: TemplateNormalizer,
    parser: IndicatorsParamsParser = default_indicators_params_parser,
    settings: Settings | None = None,
) -> IndicatorsParamsIngestSummary:
    """Parse + store the indicators/parameters file for a run."""
    settings = settings or get_settings()

    result = parser.parse(data, normalize=normalize)
    if result.errors or result.params is None:
        raise FileRejectedError(
            "indicators/parameters file rejected",
            details=[e.model_dump() for e in result.errors],
        )

    run_file = store_run_file(
        db,
        run_id=run_id,
        role=RunFileRole.indicators_params,
        filename=filename,
        data=data,
        settings=settings,
    )
    db.commit()
    db.refresh(run_file)
    logger.info("ingested indicators/params for run=%s from %s", run_id, filename)
    return IndicatorsParamsIngestSummary(
        run_file=RunFileOut.model_validate(run_file),
        params=result.params,
    )


def list_run_files(db: Session, run_id: int) -> list[RunFile]:
    return list(
        db.scalars(
            select(RunFile).where(RunFile.run_id == run_id).order_by(RunFile.id)
        )
    )


def list_facts(db: Session, run_id: int, *, limit: int = 500) -> list[Fact]:
    return list(
        db.scalars(
            select(Fact).where(Fact.run_id == run_id).order_by(Fact.id).limit(limit)
        )
    )
