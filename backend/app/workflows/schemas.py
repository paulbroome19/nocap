"""Pydantic schemas for workflow orchestration boundaries."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.facts.schemas import RunFileOut
from app.validation.schemas import FindingOut
from app.workflows.models import RunStatus


class WorkflowConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    framework_code: str
    module_code: str
    category: str | None
    is_active: bool


class WorkflowSettingsUpdate(BaseModel):
    """Settings-page update for a workflow: its category and active flag."""

    category: str | None = None
    is_active: bool


class RunSummaryOut(BaseModel):
    """Minimal run info for last-activity chips."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    reference_date: date
    status: RunStatus
    created_at: datetime


class CategoryOut(BaseModel):
    """A reporting category with its active-suite count + latest activity."""

    category: str
    active_count: int
    last_run: RunSummaryOut | None


class SuiteSummaryOut(WorkflowConfigOut):
    """A suite plus its most recent run (for the category page)."""

    last_run: RunSummaryOut | None


class EntityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    lei: str
    country: str
    default_scope: str


class EntityWrite(BaseModel):
    """Create/update payload for a reporting entity."""

    name: str
    lei: str
    country: str
    default_scope: str  # IND | CON


class EntityWorkflowConfigOut(BaseModel):
    """Per-(entity, workflow) reporting configuration."""

    model_config = ConfigDict(from_attributes=True)

    entity_id: int
    workflow_id: int
    # template code -> "true" | "false" (Auto is the absence of an entry)
    indicator_declarations: dict[str, str]
    base_currency: str | None
    decimals: int | None


class EntityWorkflowConfigWrite(BaseModel):
    indicator_declarations: dict[str, str] = {}
    base_currency: str | None = None
    decimals: int | None = None


class RunCreate(BaseModel):
    workflow_id: int
    snapshot_id: int
    reference_date: date
    entity_id: int  # scope is taken from the entity record (no per-run input)
    # Free-text instance keys describing this submission instance.
    snapshot_key: str | None = None
    adjusted_key: str | None = None
    version_key: str | None = None
    base_currency: str | None = None  # defaults to EUR
    decimals: int | None = None  # defaults to -3
    release_id: int | None = None  # defaults to the snapshot's current release


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_id: int
    snapshot_id: int
    release_id: int
    reference_date: date
    entity_id: int | None
    entity_lei: str
    entity_scope: str
    country: str
    snapshot_key: str | None
    adjusted_key: str | None
    version_key: str | None
    base_currency: str
    decimals: int
    status: RunStatus
    error: str | None
    failure_details: list | None
    created_at: datetime


class FilingIndicatorOutcome(BaseModel):
    """A derived filing-indicator outcome, with its provenance."""

    template_code: str
    reported: bool
    source: str  # "declared" | "auto"


class CheckResultOut(BaseModel):
    """One structural check category's result (the checks-executed inventory)."""

    key: str
    label: str
    status: str  # pass | warning | fail | note
    errors: int
    warnings: int
    infos: int


class FactRowOut(BaseModel):
    """An ingested fact, for the run's input-data view."""

    model_config = ConfigDict(from_attributes=True)

    template_code: str
    row_code: str
    column_code: str
    value: str
    source_sheet: str | None
    source_row: int | None


class RunDetailOut(BaseModel):
    """Run detail: the run, its files, findings, and traceability data."""

    run: RunOut
    files: list[RunFileOut]
    findings: list[FindingOut]
    fact_count: int
    filing_indicators: list[FilingIndicatorOutcome] | None
    structural_checks: list[CheckResultOut]
    formula_summary: dict | None
