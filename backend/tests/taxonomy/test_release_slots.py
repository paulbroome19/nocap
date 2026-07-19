"""Typed artifact slots on a release: readiness, backfill, upload/verify."""

from __future__ import annotations

import io
import shutil
import zipfile
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ValidationError
from app.taxonomy import artifacts, service
from app.taxonomy.models import ArtifactStatus, ReleaseSlot, SnapshotStatus


def _ready_release(db: Session, mini_dpm: Path):
    snap = service.register_snapshot(
        db, file_bytes=b"fake-accdb", filename="DPM.accdb", version_label="4.2"
    )

    def stub(src: Path, out: Path, *, settings, tables=None) -> None:
        shutil.copyfile(mini_dpm, out)

    service.ingest_snapshot(db, snap, converter=stub)
    assert snap.status is SnapshotStatus.ready
    return snap


def _zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("inner.xsd", "<schema/>")
    return buf.getvalue()


def test_slots_shape_and_dpm_reflects_snapshot(
    db_session: Session, mini_dpm: Path
) -> None:
    snap = _ready_release(db_session, mini_dpm)
    slots = {v.spec.slot: v for v in artifacts.list_slots(db_session, snap)}
    assert set(slots) == set(ReleaseSlot)

    dpm = slots[ReleaseSlot.dpm_database]
    assert dpm.spec.requirement == "required"
    assert dpm.status is ArtifactStatus.ready  # mirrors snapshot.status
    assert dpm.filename == "DPM.accdb"

    # Reference slots start empty.
    assert slots[ReleaseSlot.filing_rules].status is ArtifactStatus.empty
    assert slots[ReleaseSlot.sample_files].status is ArtifactStatus.empty


def test_readiness_tracks_required_dpm_slot(
    db_session: Session, mini_dpm: Path
) -> None:
    snap = _ready_release(db_session, mini_dpm)
    assert artifacts.release_ready(snap) is True

    # Break the DPM (required) slot -> release no longer ready, even with the
    # taxonomy slot filled.
    artifacts.store_artifact(
        db_session, snap, ReleaseSlot.taxonomy_package,
        filename="taxo.zip", data=_zip_bytes(),
    )
    service._sqlite_path(get_settings(), snap.id).unlink()
    service.verify_snapshot(db_session, snap)
    assert snap.status is SnapshotStatus.artifacts_missing
    assert artifacts.release_ready(snap) is False


def test_upload_taxonomy_slot_feeds_arelle_path(
    db_session: Session, mini_dpm: Path
) -> None:
    snap = _ready_release(db_session, mini_dpm)
    artifacts.store_artifact(
        db_session, snap, ReleaseSlot.taxonomy_package,
        filename="taxo_4.2.zip", data=_zip_bytes(),
    )
    # The file lands where formula validation reads per-snapshot taxonomy zips
    # (one active package; the on-disk name is system-generated).
    packages = service.snapshot_taxonomy_packages(get_settings(), snap.id)
    assert len(packages) == 1

    slots = {v.spec.slot: v for v in artifacts.list_slots(db_session, snap)}
    taxo = slots[ReleaseSlot.taxonomy_package]
    assert taxo.status is ArtifactStatus.ready
    assert taxo.filename == "taxo_4.2.zip"  # user filename kept for display


def test_artifact_storage_key_is_system(
    db_session: Session, mini_dpm: Path
) -> None:
    """A release artifact's on-disk key is system-generated, not the filename."""
    snap = _ready_release(db_session, mini_dpm)
    art = artifacts.store_artifact(
        db_session, snap, ReleaseSlot.taxonomy_package,
        filename="EBA taxonomy 4.2.zip", data=_zip_bytes(),
    )
    assert "taxonomy 4.2" not in art.storage_key  # independent of user filename
    assert " " not in art.storage_key
    assert art.filename == "EBA taxonomy 4.2.zip"  # kept for display
    assert (get_settings().data_dir / art.storage_key).exists()


def test_upload_replaces_previous_taxonomy_package(
    db_session: Session, mini_dpm: Path
) -> None:
    snap = _ready_release(db_session, mini_dpm)
    artifacts.store_artifact(
        db_session, snap, ReleaseSlot.taxonomy_package,
        filename="old.zip", data=_zip_bytes(),
    )
    art = artifacts.store_artifact(
        db_session, snap, ReleaseSlot.taxonomy_package,
        filename="new.zip", data=_zip_bytes(),
    )
    packages = service.snapshot_taxonomy_packages(get_settings(), snap.id)
    assert len(packages) == 1  # old one removed, one active package
    assert art.filename == "new.zip"  # display name is the latest upload


def test_backfill_materialises_existing_taxonomy_drop(
    db_session: Session, mini_dpm: Path
) -> None:
    snap = _ready_release(db_session, mini_dpm)
    # Simulate the legacy manual drop: a zip in the taxonomy dir, no row.
    slot_dir = service.snapshot_dir(get_settings(), snap.id) / "taxonomy"
    slot_dir.mkdir(parents=True, exist_ok=True)
    (slot_dir / "manual_4.2.zip").write_bytes(_zip_bytes())

    slots = {v.spec.slot: v for v in artifacts.list_slots(db_session, snap)}
    taxo = slots[ReleaseSlot.taxonomy_package]
    assert taxo.status is ArtifactStatus.ready
    assert taxo.filename == "manual_4.2.zip"


def test_upload_rejects_wrong_extension(
    db_session: Session, mini_dpm: Path
) -> None:
    snap = _ready_release(db_session, mini_dpm)
    with pytest.raises(ValidationError, match="expects"):
        artifacts.store_artifact(
            db_session, snap, ReleaseSlot.taxonomy_package,
            filename="taxo.txt", data=b"nope",
        )


def test_upload_rejects_dpm_slot(db_session: Session, mini_dpm: Path) -> None:
    snap = _ready_release(db_session, mini_dpm)
    with pytest.raises(ValidationError, match="re-ingest"):
        artifacts.store_artifact(
            db_session, snap, ReleaseSlot.dpm_database,
            filename="x.accdb", data=b"x",
        )


def test_corrupt_zip_marks_slot_failed(
    db_session: Session, mini_dpm: Path
) -> None:
    snap = _ready_release(db_session, mini_dpm)
    with pytest.raises(ValidationError, match="zip"):
        artifacts.store_artifact(
            db_session, snap, ReleaseSlot.sample_files,
            filename="samples.zip", data=b"not-a-zip",
        )
    slots = {v.spec.slot: v for v in artifacts.list_slots(db_session, snap)}
    assert slots[ReleaseSlot.sample_files].status is ArtifactStatus.failed


def test_artifacts_endpoint_returns_slots(client, db_session, mini_dpm: Path) -> None:
    # The client's get_db yields this same db_session, so a release created here
    # is visible to the endpoint.
    snap = _ready_release(db_session, mini_dpm)

    resp = client.get(f"/api/taxonomy/snapshots/{snap.id}/artifacts")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    # Only the three functional slots surface; reference slots are not shown.
    assert {s["slot"] for s in body["slots"]} == {
        "dpm_database", "taxonomy_package", "validation_rules",
    }


def test_upload_artifact_endpoint(client, db_session, mini_dpm: Path) -> None:
    snap = _ready_release(db_session, mini_dpm)
    resp = client.post(
        f"/api/taxonomy/snapshots/{snap.id}/artifacts/taxonomy_package",
        files={"file": ("taxo.zip", _zip_bytes(), "application/zip")},
    )
    assert resp.status_code == 200
    taxo = next(
        s for s in resp.json()["slots"] if s["slot"] == "taxonomy_package"
    )
    assert taxo["status"] == "ready"
    assert taxo["filename"] == "taxo.zip"
