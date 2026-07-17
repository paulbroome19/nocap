"""Pydantic schemas for the taxonomy stage.

Two groups: registry API shapes (``SnapshotOut``) and the lookup contract DTOs
(``DatapointResolution``, ``TemplateInfo``) that other stages consume via
``workflows``.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.taxonomy.models import SnapshotStatus


class SnapshotOut(BaseModel):
    """A snapshot as returned by the registry endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    version_label: str
    original_filename: str
    checksum: str
    status: SnapshotStatus
    error: str | None
    uploaded_at: datetime


class TemplateInfo(BaseModel):
    """A template (table version) within a module."""

    code: str
    name: str


class DatapointResolution(BaseModel):
    """Result of resolving a (template, row, column) triple to a datapoint.

    ``datapoint_id`` is the DPM ``VariableVID``. ``datatype_code`` is the DPM
    short code (e.g. ``m`` monetary, ``r`` decimal) — see docs/dpm-notes.md.
    """

    template_code: str
    row_code: str
    column_code: str
    datapoint_id: int
    datatype_code: str
    datatype_name: str
    period_type: str | None
    cell_code: str | None
