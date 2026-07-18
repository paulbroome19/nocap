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
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Regulator(Base):
    """A taxonomy publisher — the body that issues the DPM / taxonomy releases we
    ingest (e.g. the EBA).

    Design note: a regulator here is the *publisher* of a taxonomy, NOT a
    submission destination. Where a completed package is ultimately filed (a
    national competent authority, a specific portal) is a separate, future
    concept and must never be conflated with the publisher modelled here.
    """

    __tablename__ = "regulator"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Short stable code, e.g. "EBA".
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


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

    # The publisher of this release (e.g. EBA). Every release belongs to one.
    regulator_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("regulator.id"), index=True
    )

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


class ReleaseSlot(enum.StrEnum):
    """The typed artifact slots that make up a release.

    A release ("snapshot", historically) is now a container of typed artifacts.
    ``dpm_database`` is the release itself (the converted DPM, tracked on the
    ``TaxonomySnapshot`` row); the other three are optional attachments stored as
    ``ReleaseArtifact`` rows. See taxonomy.artifacts for the slot specs.
    """

    dpm_database = "dpm_database"
    taxonomy_package = "taxonomy_package"
    validation_rules = "validation_rules"
    filing_rules = "filing_rules"
    sample_files = "sample_files"


class ArtifactStatus(enum.StrEnum):
    """Lifecycle of a single uploaded artifact within a slot."""

    empty = "empty"
    uploaded = "uploaded"
    verifying = "verifying"
    ready = "ready"
    failed = "failed"


class ReleaseArtifact(Base):
    """One uploaded file occupying a typed slot on a release.

    The DPM slot is not stored here — it is the ``TaxonomySnapshot`` itself. This
    table holds the *other* slots (taxonomy package, filing rules, samples), one
    row per (release, slot); re-uploading a slot replaces its row.
    """

    __tablename__ = "release_artifact"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "slot", name="uq_release_artifact_slot"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("taxonomy_snapshot.id"), index=True
    )
    slot: Mapped[ReleaseSlot] = mapped_column(
        Enum(ReleaseSlot, name="release_slot")
    )
    filename: Mapped[str] = mapped_column(String(1024))
    # Path relative to the configured data dir.
    storage_key: Mapped[str] = mapped_column(String(2048))
    checksum: Mapped[str] = mapped_column(String(64))
    status: Mapped[ArtifactStatus] = mapped_column(
        Enum(ArtifactStatus, name="artifact_status"),
        default=ArtifactStatus.uploaded,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ValidationRule(Base):
    """One row of an ingested EBA validation-rules workbook (the ``validation_rules``
    slot). A projection of the workbook, sealed like the DPM SQLite: the original
    ``.xlsx`` is retained byte-for-byte on disk, this table is the queryable view.

    NOT uniquely keyed on ``(snapshot, vr_code)``: the workbook is release- and
    date-versioned, so one ``vr_code`` legitimately has several rows differing by
    module version and ``[from_reference_date, to_reference_date]`` window (e.g.
    ``v6272_m`` for COREP_OF_4.0 vs 4.2). Collapsing them would discard the very
    date-window data the register join evaluates against the run's reporting date.
    The effective row for a run is the one whose window covers its reporting date;
    ``(snapshot_id, vr_code)`` is an indexed *lookup* key, not a uniqueness one.
    """

    __tablename__ = "validation_rule"
    __table_args__ = (
        Index("ix_validation_rule_snapshot_vr", "snapshot_id", "vr_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("taxonomy_snapshot.id"), index=True
    )
    # The rule id as Arelle emits it (e.g. "v6272_m", "e4428_e") — the join key
    # to the formula run's per-rule results.
    vr_code: Mapped[str] = mapped_column(String(64))
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    frameworks: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Module tokens carry versions, e.g. "COREP_LCR_DA_4.2, FP_4.2" — parsed for
    # the coherence version cross-check.
    modules: Mapped[str | None] = mapped_column(Text, nullable=True)
    cross_module: Mapped[str | None] = mapped_column(String(8), nullable=True)
    tables: Mapped[str | None] = mapped_column(Text, nullable=True)
    expression: Mapped[str | None] = mapped_column(Text, nullable=True)
    precondition: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The human-readable rule statement joined into the run's formula register.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    from_reference_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    to_reference_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    severity: Mapped[str | None] = mapped_column(String(32), nullable=True)
