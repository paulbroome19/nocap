"""Ingestion + registry service tests (no mdbtools / Access needed).

The Access->SQLite conversion is injected: a stub converter copies the mini DPM
fixture into place, so the register -> convert -> validate -> status flow is
exercised end-to-end without the real tooling.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ConflictError, ValidationError
from app.taxonomy import service
from app.taxonomy.models import SnapshotStatus
from tests.fixtures import dpm_mini


def _register(db: Session, data: bytes = b"fake-accdb-bytes") -> object:
    return service.register_snapshot(
        db, file_bytes=data, filename="DPM.accdb", version_label="4.2"
    )


def test_register_stores_file_and_computes_checksum(db_session: Session) -> None:
    snap = _register(db_session, b"hello")
    assert snap.status is SnapshotStatus.ingesting
    assert snap.checksum == service.compute_checksum(b"hello")
    src = service._source_path(get_settings(), snap.id)
    assert src.exists() and src.read_bytes() == b"hello"


def test_duplicate_of_ready_release_rejected(db_session: Session) -> None:
    """A duplicate of a genuine, usable (ready) release is rejected."""
    snap = _register(db_session, b"same-bytes")
    snap.status = SnapshotStatus.ready  # a completed, usable release
    db_session.commit()
    with pytest.raises(ConflictError):
        _register(db_session, b"same-bytes")


def test_duplicate_of_incomplete_release_is_reclaimed(db_session: Session) -> None:
    """A duplicate of an incomplete (``ingesting``) attempt is *not* rejected —
    the stranded row is reclaimed so a stuck upload can always be retried."""
    first = _register(db_session, b"same-bytes")
    first_id = first.id
    assert first.status is SnapshotStatus.ingesting
    second = _register(db_session, b"same-bytes")  # no ConflictError
    assert second.status is SnapshotStatus.ingesting
    # The stranded attempt was purged; only the fresh registration remains.
    assert db_session.query(service.TaxonomySnapshot).count() == 1
    assert db_session.get(service.TaxonomySnapshot, first_id) is None or (
        second.id == first_id
    )


def test_empty_upload_rejected(db_session: Session) -> None:
    with pytest.raises(ValidationError):
        _register(db_session, b"")


# --- streaming (memory-safe) DPM handling ----------------------------------


def test_register_from_path_streams_and_moves_source(
    db_session: Session, tmp_path: Path
) -> None:
    """The streaming path checksums the file in chunks and *moves* it into the
    snapshot dir — never buffering it — so a ~720 MB DPM stays off the heap."""
    src = tmp_path / "upload.accdb"
    src.write_bytes(b"Standard ACE DB fake body " * 4)
    expected = service.compute_checksum_file(src)

    snap = service.register_snapshot(
        db_session, source_path=src, filename="DPM.accdb", version_label="4.2"
    )
    assert snap.status is SnapshotStatus.ingesting
    assert snap.checksum == expected
    # The temp upload was moved (consumed), and the source now lives in place.
    assert not src.exists()
    stored = service._source_path(get_settings(), snap.id)
    assert stored.exists() and service.compute_checksum_file(stored) == expected


def test_register_requires_exactly_one_source(db_session: Session) -> None:
    with pytest.raises(ValueError):
        service.register_snapshot(
            db_session, filename="DPM.accdb", version_label="4.2"
        )


def test_verify_dpm_path_accepts_access_header(tmp_path: Path) -> None:
    from app.taxonomy.models import DpmSourceForm

    p = tmp_path / "DPM.accdb"
    p.write_bytes(b"\x00\x01Standard ACE DB\x00 rest of file")
    assert (
        service.verify_dpm_path(p, "DPM.accdb") is DpmSourceForm.accdb
    )


def test_verify_dpm_path_rejects_non_access(tmp_path: Path) -> None:
    p = tmp_path / "DPM.accdb"
    p.write_bytes(b"PK\x03\x04 this is a zip, not access")
    with pytest.raises(ValidationError, match="EBA DPM"):
        service.verify_dpm_path(p, "DPM.accdb")


def test_verify_dpm_path_accepts_converted_sqlite(mini_dpm: Path) -> None:
    from app.taxonomy.models import DpmSourceForm

    assert (
        service.verify_dpm_path(mini_dpm, "dpm.sqlite") is DpmSourceForm.sqlite
    )


def test_exec_sql_stream_flushes_in_batches(tmp_path: Path) -> None:
    """Every statement lands even when the stream far exceeds one batch, and no
    statement is split across a flush."""
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.executescript("CREATE TABLE t (id INTEGER, v TEXT);")
    n = 5000
    lines = [f"INSERT INTO t (id, v) VALUES ({i}, 'row {i}');\n" for i in range(n)]
    # A tiny batch size forces many flushes over the boundary logic.
    service._exec_sql_stream(conn, iter(lines), batch_bytes=1024)
    assert conn.execute("SELECT count(*) FROM t").fetchone()[0] == n
    assert conn.execute("SELECT v FROM t WHERE id = 4999").fetchone()[0] == "row 4999"


def test_ingest_success_marks_ready_and_lookup_works(
    db_session: Session, mini_dpm: Path
) -> None:
    snap = _register(db_session)

    def stub_converter(src: Path, out: Path, *, settings, tables=None) -> None:
        shutil.copyfile(mini_dpm, out)

    service.ingest_snapshot(db_session, snap, converter=stub_converter)
    assert snap.status is SnapshotStatus.ready
    assert snap.error is None

    with service.open_lookup(snap) as lk:
        res = lk.resolve("C_67.00.a", "0020", "0060")
    assert res is not None and res.datatype_code == "m"


def test_ingest_failure_marks_failed_with_reason(db_session: Session) -> None:
    snap = _register(db_session)

    def bad_converter(src: Path, out: Path, *, settings, tables=None) -> None:
        # Produce a SQLite that is missing the required DPM tables.
        import sqlite3

        conn = sqlite3.connect(out)
        conn.execute("CREATE TABLE NotDpm (x INTEGER)")
        conn.commit()
        conn.close()

    service.ingest_snapshot(db_session, snap, converter=bad_converter)
    assert snap.status is SnapshotStatus.failed
    assert snap.error and "not a DPM database" in snap.error


def test_open_lookup_rejects_non_ready_snapshot(db_session: Session) -> None:
    snap = _register(db_session)  # still ingesting
    with pytest.raises(ValidationError):
        service.open_lookup(snap)


def test_validate_dpm_sqlite_accepts_fixture(tmp_path: Path) -> None:
    path = dpm_mini.build(tmp_path / "ok.sqlite")
    service.validate_dpm_sqlite(path)  # should not raise


# --- pre-converted SQLite as an alternative DPM input ----------------------


def _dpm_sqlite_bytes(tmp_path: Path) -> bytes:
    return dpm_mini.build(tmp_path / "dpm.sqlite").read_bytes()


def test_verify_dpm_file_accepts_access() -> None:
    from app.taxonomy.models import DpmSourceForm

    data = b"\x00\x01Standard ACE DB\x00" + b"\x00" * 64
    assert (
        service.verify_dpm_file(data, "DPM.accdb") is DpmSourceForm.accdb
    )


def test_verify_dpm_file_accepts_converted_sqlite(tmp_path: Path) -> None:
    from app.taxonomy.models import DpmSourceForm

    data = _dpm_sqlite_bytes(tmp_path)
    assert (
        service.verify_dpm_file(data, "dpm.sqlite") is DpmSourceForm.sqlite
    )


def test_verify_dpm_file_rejects_non_dpm_sqlite(tmp_path: Path) -> None:
    import sqlite3

    p = tmp_path / "other.sqlite"
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE NotDpm (x INTEGER)")
    conn.commit()
    conn.close()
    with pytest.raises(ValidationError) as exc:
        service.verify_dpm_file(p.read_bytes(), "other.sqlite")
    assert "not a converted EBA DPM database" in str(exc.value)


def test_verify_dpm_file_rejects_sqlite_named_file_that_isnt_sqlite() -> None:
    with pytest.raises(ValidationError) as exc:
        service.verify_dpm_file(b"just some text, not a database", "fake.sqlite")
    assert "not a SQLite database" in str(exc.value)


def test_verify_dpm_file_rejects_unknown_extension() -> None:
    with pytest.raises(ValidationError) as exc:
        service.verify_dpm_file(b"whatever", "release.zip")
    assert ".accdb" in str(exc.value) and ".sqlite" in str(exc.value)


def test_sqlite_form_ingests_by_copy_without_mdbtools(
    db_session: Session, tmp_path: Path
) -> None:
    """A pre-converted SQLite is adopted as the query DB — no converter is run."""
    from app.taxonomy.models import DpmSourceForm

    data = _dpm_sqlite_bytes(tmp_path)
    snap = service.register_snapshot(
        db_session,
        file_bytes=data,
        filename="dpm.sqlite",
        version_label="4.2",
        source_form=DpmSourceForm.sqlite,
    )
    assert snap.dpm_source_form is DpmSourceForm.sqlite
    # Original stored under source.sqlite, not source.accdb.
    src = service._source_path(get_settings(), snap.id, DpmSourceForm.sqlite)
    assert src.exists() and src.read_bytes() == data

    def fail_converter(*a, **k):  # must never be called for the sqlite form
        raise AssertionError("mdbtools converter should not run for sqlite input")

    service.ingest_snapshot(db_session, snap, converter=fail_converter)
    assert snap.status is SnapshotStatus.ready
    with service.open_lookup(snap) as lk:
        res = lk.resolve("C_67.00.a", "0020", "0060")
    assert res is not None and res.datatype_code == "m"
