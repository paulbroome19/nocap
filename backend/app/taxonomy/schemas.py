"""Pydantic schemas for the taxonomy stage.

Two groups: registry API shapes (``SnapshotOut``) and the lookup contract DTOs
(``DatapointResolution``, ``TemplateInfo``) that other stages consume via
``workflows``.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.taxonomy.models import ArtifactStatus, ReleaseSlot, SnapshotStatus


class CapabilitySetOut(BaseModel):
    """A release's derived capabilities (computed on read, never stored)."""

    resolve: bool
    generate: bool
    verified_entry_points: bool
    formula_validate: bool
    rule_register: bool


class SnapshotOut(BaseModel):
    """A snapshot (release) as returned by the registry endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    version_label: str
    original_filename: str
    checksum: str
    status: SnapshotStatus
    error: str | None
    uploaded_at: datetime
    # Populated by endpoints that compute it (registry list / detail); the
    # run-creation release picker shows a compact indicator from it.
    capabilities: CapabilitySetOut | None = None


class ReleaseSlotOut(BaseModel):
    """One typed artifact slot on a release, with its current occupant."""

    slot: ReleaseSlot
    label: str
    requirement: str  # required | formula | reference
    accept: list[str]
    description: str
    status: ArtifactStatus
    filename: str | None
    checksum: str | None
    error: str | None
    uploaded_at: datetime | None


class ReleaseDetailOut(BaseModel):
    """A release plus its readiness, typed slots, capabilities, and warnings."""

    release: SnapshotOut
    ready: bool
    slots: list[ReleaseSlotOut]
    capabilities: CapabilitySetOut
    # Cross-artifact version-mismatch warnings (never a block).
    coherence_warnings: list[str] = []


class TemplateInfo(BaseModel):
    """A template (table version) within a module."""

    code: str
    name: str


class ModuleMetadata(BaseModel):
    """Identity of a module within a snapshot, for package generation."""

    module_code: str
    framework_code: str
    module_version: str  # e.g. "3.3.0"
    name: str


class DatapointResolution(BaseModel):
    """Result of resolving a (template, row, column) triple to a datapoint.

    ``datapoint_id`` is the DPM ``VariableID`` — the key the EBA taxonomy uses
    for its xBRL-CSV property groups (emitted as ``dp{id}``), so generated facts
    actually load in Arelle. ``datatype_code`` is the DPM short code (e.g. ``m``
    monetary, ``r`` decimal) — see docs/dpm-notes.md.
    """

    template_code: str
    row_code: str
    column_code: str
    datapoint_id: int
    datatype_code: str
    datatype_name: str
    period_type: str | None
    cell_code: str | None
