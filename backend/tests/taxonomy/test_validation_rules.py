"""Validation-rules workbook: header verification, ingestion, register view."""

from __future__ import annotations

import io
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ValidationError
from app.taxonomy import rules
from app.taxonomy.models import (
    ArtifactStatus,
    ReleaseSlot,
    SnapshotStatus,
    TaxonomySnapshot,
    ValidationRule,
)
from tests.fixtures import validation_rules_mini as fx


@pytest.fixture
def ready_release(db_session: Session) -> TaxonomySnapshot:
    snap = TaxonomySnapshot(
        version_label="4.2",
        original_filename="dpm.accdb",
        checksum="rulescheck",
        status=SnapshotStatus.ready,
    )
    db_session.add(snap)
    db_session.commit()
    db_session.refresh(snap)
    return snap


def _ingest(db_session: Session, snap: TaxonomySnapshot) -> None:
    rules.store_workbook(
        db_session, snap, filename="rules.xlsx", data=fx.build_bytes()
    )
    rules.ingest_validation_rules(db_session, snap)


# --- header verification ---------------------------------------------------


def test_header_accepts_real_shape() -> None:
    header = rules.verify_workbook_header(fx.build_bytes())
    # 15 columns incl. the "Precondtion" misspelling + trailing extras.
    assert len(header) == 15


def test_header_rejects_wrong_file() -> None:
    import openpyxl

    wb = openpyxl.Workbook()
    wb.active.append(["Not", "The", "Rules", "File"])
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(ValidationError, match="column 1 should be 'VR Code'"):
        rules.verify_workbook_header(buf.getvalue())


def test_header_rejects_non_xlsx_bytes() -> None:
    with pytest.raises(ValidationError, match="not a readable"):
        rules.verify_workbook_header(b"this is not a workbook")


# --- parsing ---------------------------------------------------------------


def test_parse_types_dates_and_activity() -> None:
    mappings = rules.parse_workbook_rows(1, fx.build_bytes())
    assert len(mappings) == 7  # blank/trailing rows skipped
    by_code = {m["vr_code"]: m for m in mappings if m["vr_code"] != "v30000_m"}

    active = by_code["v10000_m"]
    assert active["is_active"] is True
    assert active["from_reference_date"] == date(2026, 3, 31)
    assert active["to_reference_date"] is None  # "NULL" → None
    assert active["modules"] == "COREP_LCR_DA_4.2"

    inactive = by_code["v20000_m"]
    assert inactive["is_active"] is False

    windowed = by_code["v10001_m"]
    assert windowed["to_reference_date"] == date(2026, 12, 30)


# --- ingestion (background-job shape: slot status verifying → ready) --------


def test_store_marks_slot_verifying(
    db_session: Session, ready_release: TaxonomySnapshot
) -> None:
    artifact = rules.store_workbook(
        db_session, ready_release, filename="rules.xlsx", data=fx.build_bytes()
    )
    assert artifact.slot is ReleaseSlot.validation_rules
    assert artifact.status is ArtifactStatus.verifying
    assert artifact.checksum  # sealed
    assert not rules.has_ingested_rules(db_session, ready_release.id)


def test_ingest_populates_rows_and_readies_slot(
    db_session: Session, ready_release: TaxonomySnapshot
) -> None:
    _ingest(db_session, ready_release)

    assert rules.has_ingested_rules(db_session, ready_release.id)
    count = (
        db_session.query(ValidationRule)
        .filter_by(snapshot_id=ready_release.id)
        .count()
    )
    assert count == 7

    from app.taxonomy.models import ReleaseArtifact

    artifact = (
        db_session.query(ReleaseArtifact)
        .filter_by(snapshot_id=ready_release.id, slot=ReleaseSlot.validation_rules)
        .one()
    )
    assert artifact.status is ArtifactStatus.ready


def test_reingest_replaces_rows(
    db_session: Session, ready_release: TaxonomySnapshot
) -> None:
    _ingest(db_session, ready_release)
    _ingest(db_session, ready_release)  # again — must not duplicate
    count = (
        db_session.query(ValidationRule)
        .filter_by(snapshot_id=ready_release.id)
        .count()
    )
    assert count == 7


def test_ingest_missing_file_fails_slot(
    db_session: Session, ready_release: TaxonomySnapshot
) -> None:
    settings = get_settings()
    rules.store_workbook(
        db_session, ready_release, filename="rules.xlsx", data=fx.build_bytes()
    )
    # Remove the stored original so ingestion fails.
    (settings.data_dir / "snapshots" / str(ready_release.id) / "rules"
     / "rules.xlsx").unlink()
    rules.ingest_validation_rules(db_session, ready_release)

    from app.taxonomy.models import ReleaseArtifact

    artifact = (
        db_session.query(ReleaseArtifact)
        .filter_by(snapshot_id=ready_release.id, slot=ReleaseSlot.validation_rules)
        .one()
    )
    assert artifact.status is ArtifactStatus.failed
    assert artifact.error


# --- register view: descriptions + date-range deactivation -----------------


def test_register_view_joins_descriptions(
    db_session: Session, ready_release: TaxonomySnapshot
) -> None:
    _ingest(db_session, ready_release)
    view = rules.build_register_view(db_session, ready_release.id, fx.D_CURRENT)
    assert view.descriptions["v10000_m"] == "{C 72.00.a, r0010} >= 0"


def test_register_view_effective_row_by_date(
    db_session: Session, ready_release: TaxonomySnapshot
) -> None:
    _ingest(db_session, ready_release)
    now = rules.build_register_view(db_session, ready_release.id, fx.D_CURRENT)
    earlier = rules.build_register_view(db_session, ready_release.id, fx.D_EARLIER)
    # v30000_m has two windows; the covering row differs by reporting date.
    assert now.descriptions["v30000_m"] == "v30000 new (4.2)"
    assert earlier.descriptions["v30000_m"] == "v30000 old (4.0)"


def test_register_view_date_range_deactivation(
    db_session: Session, ready_release: TaxonomySnapshot
) -> None:
    _ingest(db_session, ready_release)
    now = rules.build_register_view(db_session, ready_release.id, fx.D_CURRENT)
    earlier = rules.build_register_view(db_session, ready_release.id, fx.D_EARLIER)

    # Inactive → always deactivated.
    assert "v20000_m" in now.deactivated_codes
    # Future-dated → deactivated now, at D_CURRENT (window starts 2027).
    assert "v40000_m" in now.deactivated_codes
    # v10001_m's window (2025-12-31 …) excludes the earlier date but not now.
    assert "v10001_m" not in now.deactivated_codes
    assert "v10001_m" in earlier.deactivated_codes
    # Active LCR rule is never deactivated at its own reporting date.
    assert "v10000_m" not in now.deactivated_codes
