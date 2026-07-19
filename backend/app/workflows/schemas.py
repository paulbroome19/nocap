"""Pydantic schemas for workflow orchestration boundaries."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.facts.schemas import RunFileOut
from app.generation.schemas import OutputFormat
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
    # template code -> "required" | "not_required" (Optional is absent)
    indicator_declarations: dict[str, str]
    base_currency: str | None
    decimals: int | None


class EntityWorkflowConfigWrite(BaseModel):
    indicator_declarations: dict[str, str] = {}
    base_currency: str | None = None
    decimals: int | None = None


class RegulatorFormatOut(BaseModel):
    """A regulator's default output format."""

    regulator_id: int
    output_format: OutputFormat


class WorkflowFormatOut(BaseModel):
    """The output format for a (regulator, workflow) pair.

    ``output_format`` is always the effective format (override, else the
    regulator default, else the built-in). ``overridden`` says whether a
    per-workflow override is set; ``regulator_default`` is what applies without
    one.
    """

    regulator_id: int
    workflow_id: int
    output_format: OutputFormat
    overridden: bool
    regulator_default: OutputFormat


class OutputFormatWrite(BaseModel):
    output_format: OutputFormat


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


class ReexecuteRequest(BaseModel):
    """Body for re-executing an instance.

    When the entity or release has changed since the last execution, resolve it
    by either choosing a current dependency (``entity_id`` / ``release_snapshot_id``)
    or, for a still-usable change, ``acknowledge_changes=True``. A vanished
    dependency must be reselected.
    """

    acknowledge_changes: bool = False
    entity_id: int | None = None  # a replacement entity
    release_snapshot_id: int | None = None  # a replacement release (snapshot)


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_id: int
    snapshot_id: int
    release_id: int
    reference_date: date
    entity_id: int | None
    # Entity values frozen at execution — read these, never the live entity.
    entity_name: str | None
    entity_lei: str
    entity_scope: str
    country: str
    snapshot_key: str | None
    adjusted_key: str | None
    version_key: str | None
    base_currency: str
    decimals: int
    # The format the package was generated in; null until the run generates.
    output_format: OutputFormat | None
    status: RunStatus
    error: str | None
    failure_details: list | None
    # The release capability set captured when the run was created.
    capabilities: dict | None
    created_at: datetime


class FilingIndicatorOutcome(BaseModel):
    """A derived filing-indicator outcome, with its provenance."""

    template_code: str
    reported: bool
    source: str  # "declared" | "auto"


class RegisterRowOut(BaseModel):
    """One row of the validation rule register (structural or formula)."""

    id: str
    rule: str
    source: str  # structural | formula
    template: str | None
    data_evaluated: str
    result: str  # PASSED | FAILED | WARNING | NOTE | DEACTIVATED
    detail: str
    rule_text: str | None = None
    description: str | None = None  # plain-English provenance (structural)
    severity: str | None = None  # error | warning | info | None (unknown)
    blocking: bool = False
    evaluations: list | None = None  # per-evaluation detail (formula)
    satisfied: int | None = None
    not_satisfied: int | None = None


class FactRowOut(BaseModel):
    """An ingested fact, for the run's input-data view."""

    model_config = ConfigDict(from_attributes=True)

    template_code: str
    row_code: str
    column_code: str
    value: str
    source_sheet: str | None
    source_row: int | None


class VerdictOut(BaseModel):
    """The submission verdict + the reasoning shown in the status banner."""

    label: str  # Submittable | Not submittable | Validating | Run failed
    submittable: bool | None  # None while validation is still in progress
    blocking: int
    non_blocking_failures: int
    warnings: int
    unknown_severity: int
    severity_known: bool
    reasoning: str  # e.g. "0 blocking errors · 6 non-blocking rule failures"
    status: str


class RunDetailOut(BaseModel):
    """Run detail: the run, its files, findings, and traceability data."""

    run: RunOut
    files: list[RunFileOut]
    findings: list[FindingOut]
    fact_count: int
    filing_indicators: list[FilingIndicatorOutcome] | None
    rule_register: list[RegisterRowOut]
    formula_summary: dict | None
    verdict: VerdictOut


class ModuleVersionOption(BaseModel):
    """One selectable taxonomy version for a module — a distinct
    ``(module_version, framework_version)`` across every ready release.

    The dropdown shows ``module_version`` alone; the rest is supporting detail
    (which releases provide it, its reference-date window, the framework
    version). ``snapshot_id`` is the release a run binds to when this option is
    chosen (the newest release providing the version) — detail, not a choice."""

    module_code: str
    module_name: str | None
    module_version: str
    framework_version: str
    snapshot_id: int
    valid_from: date | None
    valid_to: date | None
    provided_by: list[str]  # release display names, newest first


class ModuleVersionOptions(BaseModel):
    """The taxonomy versions available for a reporting suite. Empty when no
    ready release contains the module — the suite cannot be run yet."""

    workflow_id: int
    module_code: str
    options: list[ModuleVersionOption]


class ReleaseProvision(BaseModel):
    """What a release provides for one enabled reporting suite, and whether that
    is new to the estate. ``already_from`` names the earliest release that first
    provided this same version (present only when not new)."""

    module_code: str
    module_name: str | None
    workflow_name: str
    module_version: str | None  # None when the release doesn't contain the module
    framework_version: str | None
    is_new: bool
    already_from: str | None


class ReleaseProvisionsSummary(BaseModel):
    """The ingestion summary: per enabled suite, what this release provides."""

    snapshot_id: int
    provisions: list[ReleaseProvision]
