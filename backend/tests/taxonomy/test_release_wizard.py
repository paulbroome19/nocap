"""All-or-nothing release creation, per-file verification, and deletion guard."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, ValidationError
from app.taxonomy import artifacts, service
from app.taxonomy.models import (
    ArtifactStatus,
    ReleaseSlot,
    SnapshotStatus,
    ValidationRule,
)
from app.taxonomy.seed import eba
from tests.fixtures import release_files as rf


def _create(db: Session, **over):
    kw = dict(
        regulator_id=eba(db).id,
        version_label="4.2",
        dpm_bytes=rf.dpm_bytes(),
        dpm_filename="DPM.accdb",
        taxonomy_bytes=rf.taxonomy_zip_bytes(),
        taxonomy_filename="taxo.zip",
        rules_bytes=rf.rules_bytes(),
        rules_filename="rules.xlsx",
    )
    kw.update(over)
    return service.create_release(db, **kw)


# --- all-or-nothing happy path ---------------------------------------------


def test_create_release_persists_all_three(db_session: Session) -> None:
    snap = _create(db_session)
    assert snap.status is SnapshotStatus.ingesting

    slots = {v.spec.slot: v for v in artifacts.list_slots(db_session, snap)}
    assert slots[ReleaseSlot.dpm_database].status is ArtifactStatus.verifying
    assert slots[ReleaseSlot.taxonomy_package].status is ArtifactStatus.ready
    assert slots[ReleaseSlot.validation_rules].status is ArtifactStatus.verifying


def test_create_release_accepts_pre_converted_sqlite(
    db_session: Session, tmp_path: Path
) -> None:
    """The DPM slot accepts a pre-converted SQLite; provenance records the form."""
    from app.taxonomy.models import DpmSourceForm
    from tests.fixtures import dpm_mini

    dpm_sqlite = dpm_mini.build(tmp_path / "dpm.sqlite").read_bytes()
    snap = _create(
        db_session, dpm_bytes=dpm_sqlite, dpm_filename="dpm.sqlite"
    )
    assert snap.status is SnapshotStatus.ingesting
    assert snap.dpm_source_form is DpmSourceForm.sqlite

    # Finalises to ready without any mdbtools converter running.
    def fail(*a, **k):
        raise AssertionError("converter should not run for the sqlite form")

    service.finalize_release(db_session, snap, converter=fail)
    assert snap.status is SnapshotStatus.ready


def test_create_release_rejects_non_dpm_sqlite(
    db_session: Session, tmp_path: Path
) -> None:
    import sqlite3

    p = tmp_path / "junk.sqlite"
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE Nope (x INTEGER)")
    conn.commit()
    conn.close()
    with pytest.raises(ValidationError):
        _create(db_session, dpm_bytes=p.read_bytes(), dpm_filename="junk.sqlite")
    # Nothing was persisted.
    assert service.list_snapshots(db_session) == []


def test_finalize_makes_release_ready(db_session: Session, mini_dpm: Path) -> None:
    snap = _create(db_session)

    def stub(src: Path, out: Path, *, settings, tables=None) -> None:
        shutil.copyfile(mini_dpm, out)

    service.finalize_release(db_session, snap, converter=stub)
    assert snap.status is SnapshotStatus.ready
    # The rules workbook was ingested as part of finalisation.
    n = (
        db_session.query(ValidationRule)
        .filter_by(snapshot_id=snap.id)
        .count()
    )
    assert n > 0


# --- per-file verification: nothing persists on any failure ----------------


@pytest.mark.parametrize(
    "over,expected",
    [
        ({"dpm_bytes": b"not an access file at all"}, "DPM database"),
        ({"dpm_filename": "DPM.zip"}, "DPM database"),
        ({"taxonomy_bytes": b"not a zip"}, "taxonomy package"),
        ({"taxonomy_filename": "taxo.txt"}, "taxonomy package"),
        ({"rules_bytes": b"not a workbook"}, "validation-rules workbook"),
        ({"rules_filename": "rules.csv"}, "validation-rules workbook"),
        ({"version_label": "   "}, "version label"),
    ],
)
def test_verification_failure_persists_nothing(
    db_session: Session, over, expected
) -> None:
    with pytest.raises(ValidationError, match=expected):
        _create(db_session, **over)
    # Airtight: no release row, no on-disk directory.
    assert service.list_snapshots(db_session) == []


def test_taxonomy_zip_without_package_is_rejected(db_session: Session) -> None:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "just notes, no taxonomy")
    with pytest.raises(ValidationError, match="taxonomyPackage.xml"):
        _create(db_session, taxonomy_bytes=buf.getvalue())
    assert service.list_snapshots(db_session) == []


# --- deletion guard ---------------------------------------------------------


def test_delete_release_with_no_runs(db_session: Session, settings=None) -> None:
    from app.core.config import get_settings

    snap = _create(db_session)
    snap_id = snap.id
    assert service.snapshot_dir(get_settings(), snap_id).exists()

    service.delete_release(db_session, snap, run_count=0)
    assert db_session.get(type(snap), snap_id) is None
    assert not service.snapshot_dir(get_settings(), snap_id).exists()


def test_delete_release_blocked_by_runs(db_session: Session) -> None:
    snap = _create(db_session)
    with pytest.raises(ConflictError, match="cannot be deleted"):
        service.delete_release(db_session, snap, run_count=3)
    # Still present.
    assert db_session.get(type(snap), snap.id) is not None


# --- endpoint: per-file failure → 400 with plain language, nothing listed ---


@pytest.fixture(autouse=True)
def _no_background_finalize(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "finalize_release_task", lambda snapshot_id: None)


def test_endpoint_rejects_bad_dpm(client: TestClient, db_session: Session) -> None:
    resp = client.post(
        "/api/taxonomy/releases",
        data={"version_label": "4.2", "regulator_id": eba(db_session).id},
        files={
            "dpm_file": ("DPM.accdb", b"garbage", "application/octet-stream"),
            "taxonomy_file": ("t.zip", rf.taxonomy_zip_bytes(), "application/zip"),
            "rules_file": ("r.xlsx", rf.rules_bytes(), "application/octet-stream"),
        },
    )
    # ValidationError → 422 with a plain-language reason; nothing was created.
    assert resp.status_code == 422
    assert "EBA DPM" in resp.json()["error"]["message"]
    assert client.get("/api/taxonomy/snapshots").json() == []


def test_endpoint_delete_no_runs_returns_204(
    client: TestClient, db_session: Session
) -> None:
    snap = _create(db_session)
    resp = client.delete(f"/api/taxonomy/snapshots/{snap.id}")
    assert resp.status_code == 204
    assert client.get(f"/api/taxonomy/snapshots/{snap.id}").status_code == 404
