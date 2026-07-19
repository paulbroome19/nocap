"""Storage keys are system-generated, not derived from user filenames (E1)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.facts import service as facts
from app.facts.models import RunFileRole


def test_run_file_key_is_system_and_independent_of_filename(
    db_session: Session,
) -> None:
    s = get_settings()
    f = facts.store_run_file(
        db_session, run_id=1, role=RunFileRole.fact_input,
        filename="Q4 facts.xlsx", data=b"data", settings=s,
    )
    db_session.commit()
    # The key does not embed the user's filename; the filename is kept for display.
    assert "facts" not in f.storage_key
    assert " " not in f.storage_key
    assert f.filename == "Q4 facts.xlsx"
    # The extension is preserved on the system name.
    assert f.storage_key.endswith(".xlsx")
    assert (s.data_dir / f.storage_key).read_bytes() == b"data"


def test_identical_filenames_coexist(db_session: Session) -> None:
    s = get_settings()
    a = facts.store_run_file(
        db_session, run_id=7, role=RunFileRole.fact_input,
        filename="facts.xlsx", data=b"first", settings=s,
    )
    b = facts.store_run_file(
        db_session, run_id=7, role=RunFileRole.fact_input,
        filename="facts.xlsx", data=b"second", settings=s,
    )
    db_session.commit()
    # Two uploads of the same name to the same run + role do NOT overwrite.
    assert a.storage_key != b.storage_key
    assert (s.data_dir / a.storage_key).read_bytes() == b"first"
    assert (s.data_dir / b.storage_key).read_bytes() == b"second"


def test_upsert_rewrites_in_place_at_stable_key(db_session: Session) -> None:
    s = get_settings()
    first = facts.upsert_run_file(
        db_session, run_id=3, role=RunFileRole.validation_report,
        filename="report_v1.html", data=b"<p>one</p>", settings=s,
    )
    key = first.storage_key
    second = facts.upsert_run_file(
        db_session, run_id=3, role=RunFileRole.validation_report,
        filename="report_v2.html", data=b"<p>two</p>", settings=s,
    )
    db_session.commit()
    # Same row + same key (stable download link); content + display name updated.
    assert second.id == first.id
    assert second.storage_key == key
    assert second.filename == "report_v2.html"
    assert (s.data_dir / key).read_bytes() == b"<p>two</p>"
