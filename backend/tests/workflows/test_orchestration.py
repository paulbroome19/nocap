"""End-to-end orchestration against the mini fixture snapshot, incl. failures."""

from __future__ import annotations

import zipfile
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ValidationError
from app.facts.models import RunFileRole
from app.taxonomy.models import SnapshotStatus, TaxonomySnapshot
from app.workflows import service
from app.workflows.models import RunStatus, WorkflowConfig
from app.workflows.seed import seed_workflow_configs
from tests.facts._xlsx import fact_xlsx
from tests.workflows.conftest import ENTITY


def _create_run(db, snapshot, workflow) -> object:
    return service.create_run(
        db,
        workflow_id=workflow.id,
        snapshot_id=snapshot.id,
        reference_date=date(2025, 12, 31),
        entity_lei=ENTITY,
        entity_scope="CON",
    )


def _attach_both(db, run_id, facts_data, indicators_data):
    service.attach_fact_file(
        db, run_id=run_id, filename="f.xlsx", data=facts_data
    )
    service.attach_indicators_params_file(
        db, run_id=run_id, filename="i.xlsx", data=indicators_data
    )


def test_full_run_generates_package(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    demo_fact_xlsx: bytes,
    demo_indicators_xlsx: bytes,
) -> None:
    run = _create_run(db_session, ready_snapshot, lcr_workflow)
    assert run.status is RunStatus.created

    service.attach_fact_file(
        db_session, run_id=run.id, filename="facts.xlsx", data=demo_fact_xlsx
    )
    db_session.refresh(run)
    assert run.status is RunStatus.files_attached

    service.attach_indicators_params_file(
        db_session, run_id=run.id, filename="ip.xlsx", data=demo_indicators_xlsx
    )

    run = service.execute_run(db_session, run.id)
    assert run.status is RunStatus.generated, run.error

    files = service.run_files(db_session, run.id)
    outputs = [f for f in files if f.role is RunFileRole.package_output]
    assert len(outputs) == 1
    assert outputs[0].filename.endswith(".zip")
    assert "COREPLCRDA" in outputs[0].filename

    # The stored package is a valid zip with the expected structure.
    path = get_settings().data_dir / outputs[0].storage_key
    zf = zipfile.ZipFile(path)
    assert any(n.endswith("/reports/report.json") for n in zf.namelist())
    assert any(n.endswith("/reports/c_67.00.a.csv") for n in zf.namelist())


def test_creation_timestamp_is_deterministic(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    demo_fact_xlsx: bytes,
    demo_indicators_xlsx: bytes,
) -> None:
    run = _create_run(db_session, ready_snapshot, lcr_workflow)
    _attach_both(db_session, run.id, demo_fact_xlsx, demo_indicators_xlsx)

    def outputs():
        files = service.run_files(db_session, run.id)
        return [f for f in files if f.role is RunFileRole.package_output]

    r1 = service.execute_run(db_session, run.id)
    name1 = outputs()[0].filename
    # Re-execute -> same filename (timestamp derived from run id + ref date).
    r2 = service.execute_run(db_session, run.id)
    name2 = outputs()[0].filename
    assert r1.status is RunStatus.generated and r2.status is RunStatus.generated
    assert name1 == name2


def test_unresolvable_fact_fails_run_with_details(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    demo_indicators_xlsx: bytes,
) -> None:
    run = _create_run(db_session, ready_snapshot, lcr_workflow)
    # A cell that does not exist in the mini DPM.
    bad = fact_xlsx([("C_67.00.a", "9999", "9999", 1)])
    service.attach_fact_file(db_session, run_id=run.id, filename="f.xlsx", data=bad)
    service.attach_indicators_params_file(
        db_session, run_id=run.id, filename="i.xlsx", data=demo_indicators_xlsx
    )

    run = service.execute_run(db_session, run.id)
    assert run.status is RunStatus.failed
    assert run.failure_details
    assert run.failure_details[0]["template"] == "C_67.00.a"


def test_execute_without_indicators_rejected(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    demo_fact_xlsx: bytes,
) -> None:
    run = _create_run(db_session, ready_snapshot, lcr_workflow)
    service.attach_fact_file(
        db_session, run_id=run.id, filename="f.xlsx", data=demo_fact_xlsx
    )
    with pytest.raises(ValidationError, match="indicators/parameters"):
        service.execute_run(db_session, run.id)


def test_create_run_rejects_non_ready_snapshot(
    db_session: Session, lcr_workflow: WorkflowConfig
) -> None:
    snap = TaxonomySnapshot(
        version_label="2.0",
        original_filename="x",
        checksum="c" * 64,
        status=SnapshotStatus.ingesting,
    )
    db_session.add(snap)
    db_session.commit()
    with pytest.raises(ValidationError, match="not ready"):
        _create_run(db_session, snap, lcr_workflow)


def test_create_run_rejects_module_not_in_snapshot(
    db_session: Session, ready_snapshot: TaxonomySnapshot
) -> None:
    wf = WorkflowConfig(
        name="COREP — Own Funds", framework_code="COREP", module_code="COREP_OF"
    )
    db_session.add(wf)
    db_session.commit()
    with pytest.raises(ValidationError, match="not in snapshot"):
        _create_run(db_session, ready_snapshot, wf)


def test_seed_is_idempotent(db_session: Session) -> None:
    assert seed_workflow_configs(db_session) == 20
    assert seed_workflow_configs(db_session) == 0
    codes = {w.module_code for w in service.list_workflows(db_session)}
    assert "COREP_LCR_DA" in codes and len(codes) == 20
