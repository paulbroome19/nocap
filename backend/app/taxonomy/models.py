"""SQLAlchemy models for the taxonomy stage.

DPM release upload, snapshot registry, datapoint lookup.

A ``TaxonomySnapshot`` is one uploaded EBA DPM release. It is sealed once
ingested: the row is never mutated except to advance its ``status``. DPM content
is not copied into Postgres — it lives on disk under the snapshot's data dir
(the raw ``.accdb`` as uploaded, plus a converted ``dpm.sqlite`` queried by the
lookup service).
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SnapshotStatus(enum.StrEnum):
    """Lifecycle of a snapshot's ingestion.

    ``artifacts_missing`` is a distinct state for a snapshot that ingested
    successfully but whose on-disk files are no longer present at the configured
    storage root (e.g. the data dir moved). It is recoverable by re-ingesting
    from the stored original — see taxonomy.service.reingest_snapshot.
    """

    ingesting = "ingesting"
    ready = "ready"
    failed = "failed"
    artifacts_missing = "artifacts_missing"


class TaxonomySnapshot(Base):
    __tablename__ = "taxonomy_snapshot"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Human label for the release, e.g. the DPM framework version "4.2".
    version_label: Mapped[str] = mapped_column(String(255))

    # The file exactly as uploaded, for provenance.
    original_filename: Mapped[str] = mapped_column(String(1024))

    # sha256 of the uploaded bytes. Unique: the same release is never ingested
    # twice (duplicates are rejected at upload).
    checksum: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    status: Mapped[SnapshotStatus] = mapped_column(
        Enum(SnapshotStatus, name="snapshot_status"),
        default=SnapshotStatus.ingesting,
    )

    # Populated when status == failed, so the UI can show why.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
