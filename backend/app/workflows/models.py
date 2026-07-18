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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


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


class WorkflowConfig(Base):
    __tablename__ = "workflow_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    framework_code: Mapped[str] = mapped_column(String(64))
    module_code: Mapped[str] = mapped_column(String(128), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
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
    # Entity is captured by reference and denormalised for reproducibility.
    entity_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("entity.id"), nullable=True
    )
    entity_lei: Mapped[str] = mapped_column(String(64))
    entity_scope: Mapped[str] = mapped_column(String(16))  # IND | CON
    country: Mapped[str] = mapped_column(String(2), default="XX")

    # Package parameters (derived defaults; overridable per run).
    base_currency: Mapped[str] = mapped_column(String(3), default="EUR")
    decimals: Mapped[int] = mapped_column(Integer, default=-3)

    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, name="run_status"), default=RunStatus.created
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_details: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Real in v2 when auth lands; nullable in v1.
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
