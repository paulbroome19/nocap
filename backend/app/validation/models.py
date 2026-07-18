"""SQLAlchemy models for the validation stage.

A ``ValidationFinding`` is one structural check result for a run. The shape is
deliberately generic — severity, code, human message, and a best-effort location
— so the v2 Arelle-based EBA formula validation emits into the same table.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Severity(enum.StrEnum):
    error = "error"
    warning = "warning"
    info = "info"


class ValidationPhase(enum.StrEnum):
    pre_generation = "pre_generation"
    post_generation = "post_generation"
    formula = "formula"  # Arelle EBA formula rules (v2)


class ValidationFinding(Base):
    __tablename__ = "validation_finding"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("run.id"), index=True
    )

    severity: Mapped[Severity] = mapped_column(
        Enum(Severity, name="finding_severity")
    )
    phase: Mapped[ValidationPhase] = mapped_column(
        Enum(ValidationPhase, name="validation_phase")
    )
    # Stable identifier, e.g. UNRESOLVED_FACT, DATATYPE_MISMATCH.
    code: Mapped[str] = mapped_column(String(64), index=True)
    message: Mapped[str] = mapped_column(Text)

    # Location — as precise as possible. Any subset may be set.
    file: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    sheet: Mapped[str | None] = mapped_column(String(255), nullable=True)
    row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    template_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    row_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    column_code: Mapped[str | None] = mapped_column(String(16), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
