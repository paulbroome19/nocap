"""SQLAlchemy models for workflow orchestration.

- ``WorkflowConfig`` — a reporting suite: a name + the framework/module it points
  at. Module codes resolve against a snapshot at run time, so a config does not
  depend on any snapshot existing.
- ``Run`` — one execution of a workflow against a specific snapshot + release,
  for an entity and reference date. Runs are never deleted; their status tracks
  the lifecycle created → files_attached → running → generated / failed.
"""

from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.generation.schemas import OutputFormat


class RunStatus(enum.StrEnum):
    """Run lifecycle.

    After the package is built, structural validation runs; a run with any
    error-severity finding ends ``failed_validation`` (the package is still
    stored, marked not-submittable). ``failed`` is an unexpected/aborted run.
    """

    created = "created"
    files_attached = "files_attached"
    running = "running"
    generated = "generated"
    failed_validation = "failed_validation"
    failed = "failed"
    # Structural validation done + package available; Arelle formula rules run in
    # the background. Findings are appended and the status finalised when done.
    formula_validation_running = "formula_validation_running"


# The reporting categories a suite can belong to. This tuple is the *curated
# display order* for the Reporting UI (capital adequacy leads, then liquidity,
# financial, and last-mile), not alphabetical — category_summaries iterates it
# directly, so the frontend renders categories in this order.
WORKFLOW_CATEGORIES = (
    "Capital",
    "Liquidity",
    "Financial",
    "Last Mile Reporting",
)


class WorkflowConfig(Base):
    __tablename__ = "workflow_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    framework_code: Mapped[str] = mapped_column(String(64))
    module_code: Mapped[str] = mapped_column(String(128), unique=True)
    # One of WORKFLOW_CATEGORIES; null for suites not surfaced in Reporting.
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Active suites appear in the Reporting UI; inactive ones only in Settings.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Entity(Base):
    """A reporting entity, selected when starting a run.

    LEI + country + default scope are captured on the run at creation, so a run
    stays reproducible even if the entity record later changes.
    """

    __tablename__ = "entity"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    lei: Mapped[str] = mapped_column(String(20), unique=True)
    country: Mapped[str] = mapped_column(String(2))  # ISO 2-letter
    default_scope: Mapped[str] = mapped_column(String(16))  # IND | CON
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class EntityWorkflowConfig(Base):
    """Per-(entity, workflow) reporting configuration.

    Reference data that shapes how a workflow reports for a specific entity:

    - ``indicator_declarations`` — a template-code → declaration map. A
      declaration is ``"optional"`` (default; report iff facts exist),
      ``"required"`` (force a positive filing indicator; the run fails if the
      template has no facts), or ``"not_required"`` (declare not-filed: force a
      negative indicator and exclude any facts for that template from the
      package). Templates absent from the map are Optional.
    - ``base_currency`` / ``decimals`` — parameter overrides used as the defaults
      when a run is created for this entity + workflow (blank ⇒ EUR / -3).

    Applied at derivation time; an uploaded indicators/params file still fully
    overrides derivation.
    """

    __tablename__ = "entity_workflow_config"
    __table_args__ = (
        UniqueConstraint(
            "entity_id", "workflow_id", name="uq_entity_workflow_config"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("entity.id"), index=True
    )
    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workflow_config.id"), index=True
    )
    indicator_declarations: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}"
    )
    base_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    decimals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RegulatorFormatDefault(Base):
    """The default output format for a regulator's submissions.

    One row per regulator. Absent ⇒ the built-in default (xBRL-CSV). A
    per-(regulator, workflow) row in ``WorkflowFormatConfig`` overrides this for
    a specific suite; see ``service.resolve_output_format``.
    """

    __tablename__ = "regulator_format_default"

    id: Mapped[int] = mapped_column(primary_key=True)
    regulator_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("regulator.id"), unique=True
    )
    output_format: Mapped[OutputFormat] = mapped_column(
        Enum(OutputFormat, name="output_format")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WorkflowFormatConfig(Base):
    """Per-(regulator, workflow) output-format override.

    Present ⇒ this suite generates in ``output_format`` regardless of the
    regulator default. Absent ⇒ the regulator default applies. Keyed on
    (regulator, workflow) so the same suite can differ by regulator.
    """

    __tablename__ = "workflow_format_config"
    __table_args__ = (
        UniqueConstraint(
            "regulator_id", "workflow_id", name="uq_workflow_format_config"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    regulator_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("regulator.id"), index=True
    )
    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workflow_config.id"), index=True
    )
    output_format: Mapped[OutputFormat] = mapped_column(
        Enum(OutputFormat, name="output_format")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Run(Base):
    __tablename__ = "run"

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workflow_config.id"), index=True
    )
    snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("taxonomy_snapshot.id"), index=True
    )
    # The explicit DPM release id within the snapshot this run is bound to.
    release_id: Mapped[int] = mapped_column(Integer)

    reference_date: Mapped[date] = mapped_column(Date)
    # Entity is captured by reference and denormalised for reproducibility. The
    # entity *values* (name, LEI, scope, country) are frozen onto the run at
    # creation so a later rename/edit/deletion of the entity never alters this
    # historical execution — surfaces read these, never the live Entity row.
    entity_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("entity.id"), nullable=True
    )
    # Nullable only for rows created before the freeze (backfilled from the
    # entity at migration time; see the migration note). New runs always set it.
    entity_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    entity_lei: Mapped[str] = mapped_column(String(64))
    # Scope is taken from the entity record at creation (no per-run input).
    entity_scope: Mapped[str] = mapped_column(String(16))  # IND | CON
    country: Mapped[str] = mapped_column(String(2), default="XX")

    # Free-text instance keys describing this submission instance. No uniqueness
    # constraint yet — identity binding arrives with the Audit stage.
    snapshot_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    adjusted_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    version_key: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Package parameters (derived defaults; overridable per run).
    base_currency: Mapped[str] = mapped_column(String(3), default="EUR")
    decimals: Mapped[int] = mapped_column(Integer, default=-3)

    # The output format the package was actually generated in, resolved from the
    # (regulator, workflow) configuration at execution time and recorded for
    # reproducibility. Null until the run generates a package.
    output_format: Mapped[OutputFormat | None] = mapped_column(
        Enum(OutputFormat, name="output_format"), nullable=True
    )

    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, name="run_status"), default=RunStatus.created
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_details: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # The derived filing-indicator outcomes for traceability: a list of
    # {template_code, reported, source} where source is "declared" | "auto".
    filing_indicators: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Formula-validation summary once the formula phase runs: {status, unsatisfied,
    # unsatisfied_rule_ids, deactivated, note}. Null until the phase runs.
    formula_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # The release capability set active when the run was created, captured for
    # reproducibility (capabilities are otherwise derived on read, never stored).
    capabilities: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # A content fingerprint of the bound release's artifacts (DPM + slot
    # checksums) at creation. A new execution of the same instance compares the
    # release's current fingerprint against this to detect that an artifact was
    # replaced, and stops for confirmation. Null on runs created before the
    # freeze (no baseline recorded — see the dependency-change guard).
    release_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )

    # Real in v2 when auth lands; nullable in v1.
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
