"""Release coherence — version cross-checks warn (never block) on mismatch."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.taxonomy import coherence, rules
from app.taxonomy.models import (
    ArtifactStatus,
    ReleaseArtifact,
    ReleaseSlot,
    SnapshotStatus,
    TaxonomySnapshot,
    ValidationRule,
)


@pytest.fixture
def release_42(db_session: Session) -> TaxonomySnapshot:
    from app.taxonomy.seed import eba

    snap = TaxonomySnapshot(
        regulator_id=eba(db_session).id,
        version_label="4.2",
        original_filename="dpm.accdb",
        checksum="coh42",
        status=SnapshotStatus.ready,
    )
    db_session.add(snap)
    db_session.commit()
    db_session.refresh(snap)
    return snap


def _add_taxo(db: Session, snap_id: int, filename: str) -> None:
    db.add(
        ReleaseArtifact(
            snapshot_id=snap_id,
            slot=ReleaseSlot.taxonomy_package,
            filename=filename,
            storage_key=f"snapshots/{snap_id}/taxonomy/{filename}",
            checksum="t",
            status=ArtifactStatus.ready,
        )
    )
    db.commit()


def _add_rule(db: Session, snap_id: int, modules: str) -> None:
    db.add(
        ValidationRule(
            snapshot_id=snap_id, vr_code="v1_m", modules=modules, is_active=True
        )
    )
    db.commit()


def test_no_warnings_when_versions_agree(
    db_session: Session, release_42: TaxonomySnapshot
) -> None:
    _add_taxo(db_session, release_42.id, "taxo_package_4.2_hotfix.zip")
    _add_rule(db_session, release_42.id, "COREP_LCR_DA_4.2, FP_4.2")
    assert coherence.coherence_warnings(db_session, release_42) == []


def test_taxonomy_version_mismatch_warns(
    db_session: Session, release_42: TaxonomySnapshot
) -> None:
    _add_taxo(db_session, release_42.id, "taxo_package_4.1.zip")
    warnings = coherence.coherence_warnings(db_session, release_42)
    assert len(warnings) == 1
    assert "taxonomy package (version 4.1)" in warnings[0]
    assert "DPM database (version 4.2)" in warnings[0]


def test_workbook_version_mismatch_warns(
    db_session: Session, release_42: TaxonomySnapshot
) -> None:
    _add_rule(db_session, release_42.id, "COREP_LCR_DA_4.1")
    warnings = coherence.coherence_warnings(db_session, release_42)
    assert len(warnings) == 1
    assert "validation-rules workbook (versions 4.1)" in warnings[0]
    assert "DPM database's version (4.2)" in warnings[0]


def test_unversioned_taxonomy_filename_is_silent(
    db_session: Session, release_42: TaxonomySnapshot
) -> None:
    # No extractable version → no claim, no warning.
    _add_taxo(db_session, release_42.id, "taxo_package.zip")
    assert coherence.coherence_warnings(db_session, release_42) == []


def test_ingested_workbook_fixture_is_coherent_with_42(
    db_session: Session, release_42: TaxonomySnapshot
) -> None:
    # The mini workbook's module tokens are all _4.2 → coherent with a 4.2 DPM.
    from tests.fixtures import validation_rules_mini as fx

    rules.store_workbook(
        db_session, release_42, filename="rules.xlsx", data=fx.build_bytes()
    )
    rules.ingest_validation_rules(db_session, release_42)
    assert coherence.coherence_warnings(db_session, release_42) == []


# --- patch-level mismatch: the reported 4.2.1-DPM / 4.2-taxonomy bug ---------


def _write_dpm_release_code(snap_id: int, *rows: tuple[int, int, str]) -> None:
    """Write a minimal converted DPM at the snapshot's sqlite path whose only
    table is ``Release`` — enough for `_dpm_version` to read the release code.
    ``rows`` are (ReleaseID, IsCurrent, Code)."""
    import sqlite3

    from app.core.config import get_settings
    from app.taxonomy import service

    settings = get_settings()
    service.snapshot_dir(settings, snap_id).mkdir(parents=True, exist_ok=True)
    path = service._sqlite_path(settings, snap_id)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE Release "
            "(ReleaseID INTEGER PRIMARY KEY, IsCurrent INTEGER NOT NULL, Code TEXT)"
        )
        conn.executemany("INSERT INTO Release VALUES (?, ?, ?)", rows)
        conn.commit()
    finally:
        conn.close()


def test_patch_level_taxonomy_mismatch_warns(
    db_session: Session, release_42: TaxonomySnapshot
) -> None:
    """The exact reported case: the DPM's current release is 4.2.1 (from the
    release code, not the label), the taxonomy package is 4.2. This used to slip
    through because the version was truncated to major.minor."""
    # DPM says 4.2.1 (current release), taxonomy package says 4.2.
    _write_dpm_release_code(
        release_42.id, (5, 0, "4.2"), (1010000003, -1, "4.2.1")
    )
    _add_taxo(db_session, release_42.id, "taxo_package_4.2_hotfix.zip")

    warnings = coherence.coherence_warnings(db_session, release_42)
    assert len(warnings) == 1
    assert "taxonomy package (version 4.2)" in warnings[0]
    assert "DPM database (version 4.2.1)" in warnings[0]


def test_multiversion_workbook_including_dpm_version_is_coherent(
    db_session: Session, release_42: TaxonomySnapshot
) -> None:
    """A rules workbook spanning several releases (4.0…4.3) is coherent with a
    4.2.1 DPM as long as it *includes* 4.2.1 — it must not warn."""
    _write_dpm_release_code(release_42.id, (1010000003, -1, "4.2.1"))
    _add_taxo(db_session, release_42.id, "taxo_package_4.2.1.zip")  # taxonomy ok
    _add_rule(db_session, release_42.id, "COREP_4.0")
    _add_rule(db_session, release_42.id, "COREP_4.2")
    _add_rule(db_session, release_42.id, "COREP_4.2.1")  # includes the DPM version
    _add_rule(db_session, release_42.id, "COREP_4.3")
    assert coherence.coherence_warnings(db_session, release_42) == []


def test_workbook_missing_dpm_version_warns(
    db_session: Session, release_42: TaxonomySnapshot
) -> None:
    """A workbook that spans 4.0/4.1 but not the 4.2.1 DPM version warns."""
    _write_dpm_release_code(release_42.id, (1010000003, -1, "4.2.1"))
    _add_rule(db_session, release_42.id, "COREP_4.0")
    _add_rule(db_session, release_42.id, "COREP_4.1")
    warnings = coherence.coherence_warnings(db_session, release_42)
    assert len(warnings) == 1
    assert "does not include" in warnings[0]
    assert "(4.2.1)" in warnings[0]


def test_padding_treats_4_2_and_4_2_0_0_as_equal(
    db_session: Session, release_42: TaxonomySnapshot
) -> None:
    """A real 4.2 release: DPM label 4.2, taxonomy filename carrying 4.2.0.0 —
    must NOT warn (trailing zeros are equal)."""
    _add_taxo(
        db_session,
        release_42.id,
        "EBA_XBRL_4.2_Reporting_Frameworks_4.2.0.0.zip",
    )
    assert coherence.coherence_warnings(db_session, release_42) == []
