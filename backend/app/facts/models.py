"""SQLAlchemy models for the facts stage.

Two tables:

- ``RunFile`` — every file attached to a run (inputs and outputs), stored as
  uploaded (byte-for-byte on disk; the row records where and its checksum).
- ``Fact`` — an append-only reported value event. Never updated in place; the
  current state of a run is a *view* over its facts.

``run_id`` links both to a ``Run``. The ``Run`` table lands in the workflows
stage; until then ``run_id`` is an unconstrained integer (the FK is added with
that migration). See docs/dpm-notes.md for how the template/row/column reference
later resolves to a datapoint (that resolution is the validation stage's job,
not this one).
"""

from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class RunFileRole(enum.StrEnum):
    """What a file attached to a run is."""

    fact_input = "fact_input"
    indicators_params = "indicators_params"
    package_output = "package_output"
    validation_report = "validation_report"


class RunFile(Base):
    __tablename__ = "run_file"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True)
    role: Mapped[RunFileRole] = mapped_column(
        Enum(RunFileRole, name="run_file_role")
    )
    filename: Mapped[str] = mapped_column(String(1024))
    # Where the bytes live (path relative to the data dir, or object-store key).
    storage_key: Mapped[str] = mapped_column(String(2048))
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Fact(Base):
    """An append-only reported value.

    Carries the template/row/column reference (canonical template code, row and
    column as text so leading zeros survive), the raw value exactly as supplied,
    and the entity + reference date the value was reported for.
    """

    __tablename__ = "fact"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True)

    template_code: Mapped[str] = mapped_column(String(64))
    row_code: Mapped[str] = mapped_column(String(16))
    column_code: Mapped[str] = mapped_column(String(16))

    # Raw value as supplied; datatype parsing is the validation stage's concern.
    value: Mapped[str] = mapped_column(Text)

    entity: Mapped[str] = mapped_column(String(64))
    reference_date: Mapped[date] = mapped_column(Date)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
