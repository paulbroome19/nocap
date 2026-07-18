"""Workflows-stage test fixtures: a ready snapshot + a seeded workflow config."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.taxonomy import service as taxonomy
from app.taxonomy.models import SnapshotStatus, TaxonomySnapshot
from app.workflows.models import WorkflowConfig
from tests.facts._xlsx import fact_xlsx, indicators_params_xlsx

ENTITY = "5299001234567890ABCD"


@pytest.fixture
def ready_snapshot(db_session: Session, mini_dpm: Path) -> TaxonomySnapshot:
    """Register + ingest a snapshot whose DPM SQLite is the mini fixture."""
    snap = taxonomy.register_snapshot(
        db_session, file_bytes=b"fake-accdb", filename="DPM.accdb", version_label="2.0"
    )

    def stub(src: Path, out: Path, *, settings, tables=None) -> None:
        shutil.copyfile(mini_dpm, out)

    taxonomy.ingest_snapshot(db_session, snap, converter=stub)
    assert snap.status is SnapshotStatus.ready
    return snap


@pytest.fixture
def lcr_workflow(db_session: Session) -> WorkflowConfig:
    wf = WorkflowConfig(
        name="COREP — LCR (Delegated Act)",
        framework_code="COREP",
        module_code="COREP_LCR_DA",
        active=True,
    )
    db_session.add(wf)
    db_session.commit()
    db_session.refresh(wf)
    return wf


@pytest.fixture
def demo_fact_xlsx() -> bytes:
    # Cells that resolve in the mini DPM: (0020,0060)->monetary, (0010,0010)->pct.
    # The percentage is a ratio (<= 1) so a clean run has zero warnings.
    return fact_xlsx(
        [
            ("C_67.00.a", "0020", "0060", 100000),
            ("C_67.00.a", "0010", "0010", 0.85),
        ]
    )


@pytest.fixture
def demo_indicators_xlsx() -> bytes:
    return indicators_params_xlsx(
        [
            ("entity_lei", ENTITY),
            ("reference_date", "2025-12-31"),
            ("base_currency", "EUR"),
            ("decimals", -3),
        ],
        [("C_67.00.a", True)],
    )
