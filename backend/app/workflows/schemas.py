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
    active: bool


class RunCreate(BaseModel):
    workflow_id: int
    snapshot_id: int
    reference_date: date
    entity_lei: str
    entity_scope: str = "CON"  # IND | CON
    release_id: int | None = None  # defaults to the snapshot's current release
    country: str | None = None  # defaults to settings.default_country


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_id: int
    snapshot_id: int
    release_id: int
    reference_date: date
    entity_lei: str
    entity_scope: str
    country: str
    status: RunStatus
    error: str | None
    failure_details: list | None
    created_at: datetime


class RunDetailOut(BaseModel):
    """Run detail: the run, its attached files, and its validation findings."""

    run: RunOut
    files: list[RunFileOut]
    findings: list[FindingOut]
