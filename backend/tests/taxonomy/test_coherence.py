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
    snap = TaxonomySnapshot(
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
    assert warnings == ["taxonomy package 4.1 does not match DPM 4.2"]


def test_workbook_version_mismatch_warns(
    db_session: Session, release_42: TaxonomySnapshot
) -> None:
    _add_rule(db_session, release_42.id, "COREP_LCR_DA_4.1")
    warnings = coherence.coherence_warnings(db_session, release_42)
    assert warnings == [
        "validation-rules workbook 4.1 does not match DPM 4.2"
    ]


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
