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
    """Run lifecycle. A ``validated`` step sits between generation and finalising
    the run (see workflows.service) — currently a pass-through the validation
    stage will fill in."""

    created = "created"
    files_attached = "files_attached"
    running = "running"
    generated = "generated"
    failed = "failed"


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
    entity_lei: Mapped[str] = mapped_column(String(64))
    entity_scope: Mapped[str] = mapped_column(String(16))  # IND | CON
    country: Mapped[str] = mapped_column(String(2), default="XX")

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
