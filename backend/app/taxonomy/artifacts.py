"""Typed artifact slots for a release.

A release (a ``TaxonomySnapshot`` row) is a container of typed artifacts:

- ``dpm_database`` (required) — the EBA DPM Access file, converted to the query
  SQLite on upload. This *is* the release; its state lives on the snapshot row,
  not in ``release_artifact``.
- ``taxonomy_package`` (required for formula validation) — the XBRL taxonomy
  package zip(s). Stored under ``{snapshot_dir}/taxonomy/`` so the existing
  per-snapshot taxonomy path (used by Arelle) is fed straight from the UI.
- ``filing_rules`` (reference) — the Filing Rules PDF.
- ``sample_files`` (reference) — EBA sample files.

Release readiness = every *required* slot ready = the DPM slot ready. The
taxonomy slot only gates formula validation, so it is flagged ``formula`` rather
than ``required``.

Per the dependency rules this imports only ``app.core`` and its own stage.
"""

from __future__ import annotations

import logging
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import NotFoundError, ValidationError
from app.taxonomy.models import (
    ArtifactStatus,
    ReleaseArtifact,
    ReleaseSlot,
    SnapshotStatus,
    TaxonomySnapshot,
)
from app.taxonomy.service import (
    compute_checksum,
    snapshot_dir,
    snapshot_taxonomy_packages,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Slot specs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SlotSpec:
    slot: ReleaseSlot
    label: str
    # "required" (blocks readiness), "formula" (needed for formula validation),
    # or "reference" (informational only).
    requirement: str
    accept: tuple[str, ...]  # accepted file extensions (lowercase, with dot)
    description: str


SLOT_SPECS: tuple[SlotSpec, ...] = (
    SlotSpec(
        slot=ReleaseSlot.dpm_database,
        label="DPM database",
        requirement="required",
        accept=(".accdb", ".mdb"),
        description=(
            "EBA DPM 2.0 Access database. Converted to the query database on "
            "upload; the release is unusable until this is ready."
        ),
    ),
    SlotSpec(
        slot=ReleaseSlot.taxonomy_package,
        label="Taxonomy package",
        requirement="formula",
        accept=(".zip",),
        description=(
            "XBRL taxonomy package (or container zip). Required for Arelle "
            "formula validation; uploading here replaces the manual file drop."
        ),
    ),
    SlotSpec(
        slot=ReleaseSlot.filing_rules,
        label="Filing rules",
        requirement="reference",
        accept=(".pdf",),
        description="EBA Filing Rules document — reference only.",
    ),
    SlotSpec(
        slot=ReleaseSlot.sample_files,
        label="Sample files",
        requirement="reference",
        accept=(".zip",),
        description="EBA sample submission files — reference only.",
    ),
)

_SPEC_BY_SLOT = {s.slot: s for s in SLOT_SPECS}


def slot_spec(slot: ReleaseSlot) -> SlotSpec:
    return _SPEC_BY_SLOT[slot]


# ---------------------------------------------------------------------------
# Slot view (for the API)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SlotView:
    """A slot's spec plus its current occupant (if any)."""

    spec: SlotSpec
    status: ArtifactStatus
    filename: str | None
    checksum: str | None
    error: str | None
    uploaded_at: datetime | None


def _dpm_status(snapshot: TaxonomySnapshot) -> ArtifactStatus:
    return {
        SnapshotStatus.ingesting: ArtifactStatus.verifying,
        SnapshotStatus.ready: ArtifactStatus.ready,
        SnapshotStatus.failed: ArtifactStatus.failed,
        SnapshotStatus.artifacts_missing: ArtifactStatus.failed,
    }[snapshot.status]


def _reference_dir(settings: Settings, snapshot_id: int, slot: ReleaseSlot) -> Path:
    return snapshot_dir(settings, snapshot_id) / "reference" / slot.value


def _storage_dir(settings: Settings, snapshot_id: int, slot: ReleaseSlot) -> Path:
    if slot is ReleaseSlot.taxonomy_package:
        return snapshot_dir(settings, snapshot_id) / "taxonomy"
    return _reference_dir(settings, snapshot_id, slot)


# ---------------------------------------------------------------------------
# Backfill (migrate on-disk files of existing releases into slots)
# ---------------------------------------------------------------------------


def ensure_backfilled(
    db: Session, snapshot: TaxonomySnapshot, *, settings: Settings | None = None
) -> None:
    """Create ReleaseArtifact rows for pre-existing on-disk files (idempotent).

    Older releases have a taxonomy package dropped straight into
    ``{snapshot_dir}/taxonomy/`` with no row to describe it. Materialise a
    ``taxonomy_package`` row so it shows up in its slot.
    """
    settings = settings or get_settings()
    have = set(
        db.scalars(
            select(ReleaseArtifact.slot).where(
                ReleaseArtifact.snapshot_id == snapshot.id
            )
        )
    )
    if ReleaseSlot.taxonomy_package in have:
        return
    packages = snapshot_taxonomy_packages(settings, snapshot.id)
    if not packages:
        return
    pkg = packages[0]
    db.add(
        ReleaseArtifact(
            snapshot_id=snapshot.id,
            slot=ReleaseSlot.taxonomy_package,
            filename=pkg.name,
            storage_key=str(pkg.relative_to(settings.data_dir)),
            checksum=compute_checksum(pkg.read_bytes()),
            status=ArtifactStatus.ready,
        )
    )
    db.commit()
    logger.info(
        "backfilled taxonomy_package slot for release id=%s from %s",
        snapshot.id, pkg.name,
    )


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def list_slots(
    db: Session, snapshot: TaxonomySnapshot, *, settings: Settings | None = None
) -> list[SlotView]:
    """The four slots for a release, each with its current occupant."""
    settings = settings or get_settings()
    ensure_backfilled(db, snapshot, settings=settings)
    rows = {
        a.slot: a
        for a in db.scalars(
            select(ReleaseArtifact).where(
                ReleaseArtifact.snapshot_id == snapshot.id
            )
        )
    }
    views: list[SlotView] = []
    for spec in SLOT_SPECS:
        if spec.slot is ReleaseSlot.dpm_database:
            views.append(
                SlotView(
                    spec=spec,
                    status=_dpm_status(snapshot),
                    filename=snapshot.original_filename,
                    checksum=snapshot.checksum,
                    error=snapshot.error,
                    uploaded_at=snapshot.uploaded_at,
                )
            )
            continue
        a = rows.get(spec.slot)
        if a is None:
            views.append(
                SlotView(spec, ArtifactStatus.empty, None, None, None, None)
            )
        else:
            views.append(
                SlotView(
                    spec=spec,
                    status=a.status,
                    filename=a.filename,
                    checksum=a.checksum,
                    error=a.error,
                    uploaded_at=a.uploaded_at,
                )
            )
    return views


def release_ready(snapshot: TaxonomySnapshot) -> bool:
    """A release is ready when every *required* slot is ready.

    Only the DPM slot is required (it blocks runs); the taxonomy slot gates
    formula validation, not readiness.
    """
    return snapshot.status is SnapshotStatus.ready


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


def _verify_zip(data: bytes) -> str | None:
    """Return an error string if the bytes are not a readable zip, else None."""
    import io

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            if zf.testzip() is not None:
                return "zip archive is corrupt"
    except zipfile.BadZipFile:
        return "not a valid zip archive"
    return None


def _verify_pdf(data: bytes) -> str | None:
    return None if data[:5] == b"%PDF-" else "not a valid PDF document"


def store_artifact(
    db: Session,
    snapshot: TaxonomySnapshot,
    slot: ReleaseSlot,
    *,
    filename: str,
    data: bytes,
    settings: Settings | None = None,
) -> ReleaseArtifact:
    """Store an uploaded file into a slot, replacing any existing occupant.

    The DPM slot is not accepted here — upload the DPM when creating a release
    (and use re-ingest to rebuild it). Raises ``ValidationError`` for a bad slot,
    empty file, wrong extension, or content that fails the slot's light check.
    """
    settings = settings or get_settings()
    if slot is ReleaseSlot.dpm_database:
        raise ValidationError(
            "the DPM database is set when the release is created; use re-ingest "
            "to rebuild it"
        )
    spec = _SPEC_BY_SLOT[slot]
    if not data:
        raise ValidationError("uploaded file is empty")
    ext = Path(filename).suffix.lower()
    if ext not in spec.accept:
        raise ValidationError(
            f"{spec.label} expects {' or '.join(spec.accept)} (got {ext or 'no'} "
            "extension)"
        )

    # Light content check per slot type.
    problem = (
        _verify_pdf(data) if slot is ReleaseSlot.filing_rules else _verify_zip(data)
    )
    status = ArtifactStatus.failed if problem else ArtifactStatus.ready

    # Write bytes: taxonomy replaces the whole slot dir (single active package);
    # reference slots overwrite by filename within their own dir.
    target_dir = _storage_dir(settings, snapshot.id, slot)
    if slot is ReleaseSlot.taxonomy_package and target_dir.exists():
        for old in target_dir.glob("*.zip"):
            old.unlink()
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / filename
    path.write_bytes(data)

    artifact = db.scalar(
        select(ReleaseArtifact).where(
            ReleaseArtifact.snapshot_id == snapshot.id,
            ReleaseArtifact.slot == slot,
        )
    )
    if artifact is None:
        artifact = ReleaseArtifact(snapshot_id=snapshot.id, slot=slot)
        db.add(artifact)
    artifact.filename = filename
    artifact.storage_key = str(path.relative_to(settings.data_dir))
    artifact.checksum = compute_checksum(data)
    artifact.status = status
    artifact.error = problem
    db.commit()
    db.refresh(artifact)
    logger.info(
        "stored %s artifact for release id=%s (%s)",
        slot.value, snapshot.id, status.value,
    )
    if problem:
        raise ValidationError(f"{spec.label}: {problem}")
    return artifact


def parse_slot(value: str) -> ReleaseSlot:
    try:
        return ReleaseSlot(value)
    except ValueError as exc:
        raise NotFoundError(f"unknown slot {value!r}") from exc


def get_artifact(db: Session, artifact_id: int) -> ReleaseArtifact:
    artifact = db.get(ReleaseArtifact, artifact_id)
    if artifact is None:
        raise NotFoundError(f"artifact id={artifact_id} not found")
    return artifact
