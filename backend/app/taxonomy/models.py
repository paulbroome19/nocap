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
from sqlalchemy.orm import Mapped, mapped_column, relationship

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


class DpmSourceForm(enum.StrEnum):
    """Which input form the DPM database was supplied in — provenance.

    ``accdb`` — the original EBA DPM 2.0 Microsoft Access file, converted to the
    query SQLite on the server via mdbtools (the canonical, self-contained path).
    ``sqlite`` — a pre-converted SQLite supplied directly, for when uploading the
    ~720 MB Access file over the web is impractical (the operator converts it
    locally with the documented command). Both yield an identical query database;
    this records which route a release came in by, for the audit trail.
    """

    accdb = "accdb"
    sqlite = "sqlite"


class TaxonomySnapshot(Base):
    __tablename__ = "taxonomy_snapshot"

    id: Mapped[int] = mapped_column(primary_key=True)

    # The publisher of this release (e.g. EBA). Every release belongs to one.
    regulator_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("regulator.id"), index=True
    )
    regulator: Mapped[Regulator] = relationship(lazy="joined")

    # Human label for the release, e.g. the DPM framework version "4.2".
    version_label: Mapped[str] = mapped_column(String(255))

    # The file exactly as uploaded, for provenance.
    original_filename: Mapped[str] = mapped_column(String(1024))

    # sha256 of the uploaded bytes. Unique: the same release is never ingested
    # twice (duplicates are rejected at upload).
    checksum: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # Which form the DPM was supplied in (original .accdb vs pre-converted
    # SQLite) — provenance for the audit trail. Legacy rows default to accdb.
    dpm_source_form: Mapped[DpmSourceForm] = mapped_column(
        Enum(DpmSourceForm, name="dpm_source_form"),
        default=DpmSourceForm.accdb,
        server_default=DpmSourceForm.accdb.value,
    )

    status: Mapped[SnapshotStatus] = mapped_column(
        Enum(SnapshotStatus, name="snapshot_status"),
        default=SnapshotStatus.ingesting,
    )

    # Populated when status == failed, so the UI can show why.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    @property
    def regulator_code(self) -> str:
        return self.regulator.code

    @property
    def regulator_name(self) -> str:
        return self.regulator.name

    @property
    def display_name(self) -> str:
        """Business name for this release, e.g. "EBA Taxonomy 4.2"."""
        return f"{self.regulator.code} Taxonomy {self.version_label}"

    @property
    def dpm_source_label(self) -> str:
        """Business-readable provenance of the DPM input form."""
        return {
            DpmSourceForm.accdb: "Original EBA Access database (.accdb)",
            DpmSourceForm.sqlite: "Pre-converted DPM database (.sqlite)",
        }[self.dpm_source_form]


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


class ReleaseModule(Base):
    """A module this release *provides* — recorded at ingest from the DPM's own
    current (``IsCurrent``) release row, not its full history.

    The DPM is cumulative (it carries historical module versions too), but a
    release provides only the module versions current at its own release. These
    rows are the user-selectable surface: the version dropdown, the dedup across
    releases, and the ingestion summary all read from here — never from the raw
    DPM history. Historical module versions stay queryable via ``TaxonomyLookup``
    (existing runs depend on them) but never appear here.

    The selection key across releases is ``(module_code, module_version,
    framework_version)``: three releases that all provide COREP_LCR_DA 3.3.0 at
    framework 4.2 collapse to one option; a release that bumps a module's version
    presents a distinct one.
    """

    __tablename__ = "release_module"
    __table_args__ = (
        Index("ix_release_module_snapshot", "snapshot_id"),
        Index("ix_release_module_code", "module_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("taxonomy_snapshot.id"), index=True
    )
    # e.g. "COREP_LCR_DA" — matches WorkflowConfig.module_code.
    module_code: Mapped[str] = mapped_column(String(128))
    framework_code: Mapped[str] = mapped_column(String(64))
    module_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # ModuleVersion.VersionNumber, e.g. "3.3.0" — the module version (also the
    # version in the package filename). This is what the user selects.
    module_version: Mapped[str] = mapped_column(String(32))
    # The framework taxonomy version (major.minor of the DPM release code, e.g.
    # "4.2"): entry points are versioned at the framework level, and a DPM
    # revision (4.2.1) reuses the framework's taxonomy. Part of the dedup key.
    framework_version: Mapped[str] = mapped_column(String(32))
    # The module version's reference-date applicability window (from the DPM's
    # ModuleVersion.FromReferenceDate/ToReferenceDate). Supporting detail.
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
