"""Transactional release creation (A1), per-file verification, deletion (A2)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.taxonomy import artifacts, service
from app.taxonomy.models import (
    ArtifactStatus,
    ReleaseSlot,
    SnapshotStatus,
    ValidationRule,
)
from app.taxonomy.seed import eba
from tests.fixtures import dpm_mini
from tests.fixtures import release_files as rf
from tests.fixtures import validation_rules_mini as vr


def _stub_converter(src: Path, out: Path, *, settings, tables=None) -> None:
    """Stand in for mdbtools: write a valid mini DPM query database."""
    dpm_mini.build(out)


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
        converter=_stub_converter,
    )
    kw.update(over)
    return service.create_release(db, **kw)


# --- all-or-nothing happy path: a created release is fully ready ------------


def test_create_release_is_ready_end_to_end(db_session: Session) -> None:
    snap = _create(db_session)
    # Everything ran synchronously — the release exists only because it succeeded.
    assert snap.status is SnapshotStatus.ready

    slots = {v.spec.slot: v for v in artifacts.list_slots(db_session, snap)}
    assert slots[ReleaseSlot.dpm_database].status is ArtifactStatus.ready
    assert slots[ReleaseSlot.taxonomy_package].status is ArtifactStatus.ready
    assert slots[ReleaseSlot.validation_rules].status is ArtifactStatus.ready
    # The rules workbook was ingested as part of creation.
    n = (
        db_session.query(ValidationRule)
        .filter_by(snapshot_id=snap.id)
        .count()
    )
    assert n > 0
    # It appears in the (usable-only) list.
    assert snap.id in {s.id for s in service.list_snapshots(db_session)}


def test_create_release_accepts_pre_converted_sqlite(
    db_session: Session, tmp_path: Path
) -> None:
    """A pre-converted SQLite needs no mdbtools converter; still fully ready."""
    from app.taxonomy.models import DpmSourceForm

    dpm_sqlite = dpm_mini.build(tmp_path / "dpm.sqlite").read_bytes()

    def fail(*a, **k):
        raise AssertionError("converter must not run for the sqlite form")

    snap = _create(
        db_session, dpm_bytes=dpm_sqlite, dpm_filename="dpm.sqlite", converter=fail
    )
    assert snap.status is SnapshotStatus.ready
    assert snap.dpm_source_form is DpmSourceForm.sqlite


# --- transactional failure: no release, no residue -------------------------


def _assert_nothing_persisted(db_session: Session) -> None:
    from app.core.config import get_settings

    assert db_session.query(service.TaxonomySnapshot).count() == 0
    # No stray release directory (id 1 would be the first).
    assert not service.snapshot_dir(get_settings(), 1).exists()


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
    _assert_nothing_persisted(db_session)


def test_conversion_failure_persists_nothing(db_session: Session) -> None:
    """A DPM conversion failure (a background stage before) leaves no release."""

    def boom(src, out, *, settings, tables=None):
        raise RuntimeError("mdbtools blew up")

    with pytest.raises(ValidationError, match="could not be created"):
        _create(db_session, converter=boom)
    _assert_nothing_persisted(db_session)


def test_rule_ingestion_failure_persists_nothing(db_session: Session) -> None:
    """Rule ingestion is part of creation: if it fails, no release survives."""
    # A workbook with a valid header but no data rows passes verification, then
    # fails ingestion ("no validation rules") — previously left a failed release.
    wb = Workbook()
    ws = wb.active
    ws.append(list(vr.HEADER))
    buf = io.BytesIO()
    wb.save(buf)

    with pytest.raises(ValidationError, match="validation-rules workbook"):
        _create(db_session, rules_bytes=buf.getvalue())
    _assert_nothing_persisted(db_session)


def test_taxonomy_zip_without_package_is_rejected(db_session: Session) -> None:
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "just notes, no taxonomy")
    with pytest.raises(ValidationError, match="taxonomyPackage.xml"):
        _create(db_session, taxonomy_bytes=buf.getvalue())
    _assert_nothing_persisted(db_session)


# --- deletion: allowed regardless of runs; removes everything --------------


def test_delete_release_removes_everything(db_session: Session) -> None:
    from app.core.config import get_settings

    snap = _create(db_session)
    snap_id = snap.id
    assert service.snapshot_dir(get_settings(), snap_id).exists()

    service.delete_release(db_session, snap)
    assert db_session.get(service.TaxonomySnapshot, snap_id) is None
    assert not service.snapshot_dir(get_settings(), snap_id).exists()
    assert (
        db_session.query(ValidationRule).filter_by(snapshot_id=snap_id).count()
        == 0
    )
    # After deletion the same files upload cleanly (no leftover checksum/dir).
    again = _create(db_session)
    assert again.status is SnapshotStatus.ready


# --- endpoint: synchronous, all-or-nothing ---------------------------------


def test_endpoint_creates_ready_release(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    # Upload a pre-converted SQLite DPM so the endpoint needs no mdbtools.
    dpm_sqlite = dpm_mini.build(tmp_path / "dpm.sqlite").read_bytes()
    resp = client.post(
        "/api/taxonomy/releases",
        data={"version_label": "4.2", "regulator_id": eba(db_session).id},
        files={
            "dpm_file": ("dpm.sqlite", dpm_sqlite, "application/octet-stream"),
            "taxonomy_file": ("t.zip", rf.taxonomy_zip_bytes(), "application/zip"),
            "rules_file": ("r.xlsx", rf.rules_bytes(), "application/octet-stream"),
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "ready"
    sid = resp.json()["id"]

    # It is listed (usable), and deletes to 204.
    assert sid in {s["id"] for s in client.get("/api/taxonomy/snapshots").json()}
    assert client.delete(f"/api/taxonomy/snapshots/{sid}").status_code == 204
    assert client.get(f"/api/taxonomy/snapshots/{sid}").status_code == 404


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
    assert resp.status_code == 422
    assert "EBA DPM" in resp.json()["error"]["message"]
    assert client.get("/api/taxonomy/snapshots").json() == []
