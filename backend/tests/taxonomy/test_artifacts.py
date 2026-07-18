"""Snapshot artifact integrity + re-ingest recovery."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ValidationError
from app.taxonomy import service
from app.taxonomy.models import SnapshotStatus


def _ready_snapshot(db: Session, mini_dpm: Path):
    snap = service.register_snapshot(
        db, file_bytes=b"fake-accdb", filename="DPM.accdb", version_label="2.0"
    )

    def stub(src: Path, out: Path, *, settings, tables=None) -> None:
        shutil.copyfile(mini_dpm, out)

    service.ingest_snapshot(db, snap, converter=stub)
    assert snap.status is SnapshotStatus.ready
    return snap


def test_verify_flips_ready_to_artifacts_missing(
    db_session: Session, mini_dpm: Path
) -> None:
    snap = _ready_snapshot(db_session, mini_dpm)
    # Delete the converted DB out from under the snapshot.
    service._sqlite_path(get_settings(), snap.id).unlink()

    service.verify_snapshot(db_session, snap)
    assert snap.status is SnapshotStatus.artifacts_missing
    assert snap.error and "missing" in snap.error


def test_verify_recovers_when_artifacts_return(
    db_session: Session, mini_dpm: Path
) -> None:
    snap = _ready_snapshot(db_session, mini_dpm)
    sqlite_path = service._sqlite_path(get_settings(), snap.id)
    sqlite_path.unlink()
    service.verify_snapshot(db_session, snap)
    assert snap.status is SnapshotStatus.artifacts_missing

    shutil.copyfile(mini_dpm, sqlite_path)  # data dir corrected
    service.verify_snapshot(db_session, snap)
    assert snap.status is SnapshotStatus.ready
    assert snap.error is None


def test_verify_all_snapshots_counts_changes(
    db_session: Session, mini_dpm: Path
) -> None:
    snap = _ready_snapshot(db_session, mini_dpm)
    service._sqlite_path(get_settings(), snap.id).unlink()
    assert service.verify_all_snapshots(db_session) == 1
    assert snap.status is SnapshotStatus.artifacts_missing


def test_open_lookup_rejects_artifacts_missing(
    db_session: Session, mini_dpm: Path
) -> None:
    snap = _ready_snapshot(db_session, mini_dpm)
    service._sqlite_path(get_settings(), snap.id).unlink()
    service.verify_snapshot(db_session, snap)
    with pytest.raises(ValidationError, match="re-ingest"):
        service.open_lookup(snap)


def test_reingest_rebuilds_without_reupload(
    db_session: Session, mini_dpm: Path
) -> None:
    snap = _ready_snapshot(db_session, mini_dpm)
    service._sqlite_path(get_settings(), snap.id).unlink()
    service.verify_snapshot(db_session, snap)
    assert snap.status is SnapshotStatus.artifacts_missing

    # Re-ingest reuses the stored source.accdb — no upload, no checksum check.
    snap = service.reingest_snapshot(db_session, snap.id)
    assert snap.status is SnapshotStatus.ingesting

    def stub(src: Path, out: Path, *, settings, tables=None) -> None:
        shutil.copyfile(mini_dpm, out)

    service.ingest_snapshot(db_session, snap, converter=stub)
    assert snap.status is SnapshotStatus.ready
    with service.open_lookup(snap) as lk:
        assert lk.resolve("C_67.00.a", "0020", "0060") is not None


def test_reingest_requires_source_on_disk(
    db_session: Session, mini_dpm: Path
) -> None:
    snap = _ready_snapshot(db_session, mini_dpm)
    # Remove the stored original too — re-ingest can no longer recover.
    service._source_path(get_settings(), snap.id).unlink()
    with pytest.raises(ValidationError, match="re-upload"):
        service.reingest_snapshot(db_session, snap.id)
