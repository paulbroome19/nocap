"""Schemas for the validation stage.

``Finding`` is the DTO the checks emit (before persistence); ``FindingOut`` is the
API shape. Both mirror the generic ``ValidationFinding`` model so the future
Arelle adapter can reuse them.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.validation.models import Severity, ValidationPhase


class Finding(BaseModel):
    """A single check result (pre-persistence)."""

    severity: Severity
    phase: ValidationPhase
    code: str
    message: str
    file: str | None = None
    sheet: str | None = None
    row: int | None = None
    template_code: str | None = None
    row_code: str | None = None
    column_code: str | None = None


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    severity: Severity
    phase: ValidationPhase
    code: str
    message: str
    file: str | None
    sheet: str | None
    row: int | None
    template_code: str | None
    row_code: str | None
    column_code: str | None
