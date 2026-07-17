"""Pydantic schemas for the facts stage.

Parser output DTOs (``ParsedFact``, ``RowError``, ``IndicatorsParams``) and API
shapes (``RunFileOut``, ``FactOut``, ingest summaries).
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.facts.models import RunFileRole

# --- Fact file parsing -----------------------------------------------------


class RowError(BaseModel):
    """A precise, row-level rejection message."""

    sheet: str
    row: int  # 1-based worksheet row
    column: str | None = None
    message: str


class ParsedFact(BaseModel):
    """One parsed fact row (pre-persistence). ``template_code`` is canonical."""

    template_code: str
    template_code_raw: str
    row_code: str
    column_code: str
    value: str
    source_sheet: str
    source_row: int


class FactFileParseResult(BaseModel):
    facts: list[ParsedFact]
    errors: list[RowError]


# --- Indicators & parameters parsing ---------------------------------------


class FilingIndicator(BaseModel):
    template_code: str  # canonical
    reported: bool = True


class IndicatorsParams(BaseModel):
    filing_indicators: list[FilingIndicator]
    entity_lei: str
    reference_date: date
    base_currency: str
    decimals: int


class IndicatorsParamsParseResult(BaseModel):
    params: IndicatorsParams | None
    errors: list[RowError]


# --- API shapes ------------------------------------------------------------


class RunFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    role: RunFileRole
    filename: str
    checksum: str
    created_at: datetime


class FactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    template_code: str
    row_code: str
    column_code: str
    value: str
    entity: str
    reference_date: date


class FactIngestSummary(BaseModel):
    """Returned when a fact file is accepted."""

    run_file: RunFileOut
    fact_count: int


class IndicatorsParamsIngestSummary(BaseModel):
    """Returned when an indicators/params file is accepted."""

    run_file: RunFileOut
    params: IndicatorsParams
