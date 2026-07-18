"""Orchestration: entity-based runs, derived indicators/params, open-table guard."""

from __future__ import annotations

import zipfile
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ValidationError
from app.facts.models import RunFileRole
from app.taxonomy.models import SnapshotStatus, TaxonomySnapshot
from app.validation.models import Severity
from app.workflows import service
from app.workflows.models import Entity, RunStatus, WorkflowConfig
from app.workflows.seed import seed_entities, seed_workflow_configs
from tests.facts._xlsx import fact_xlsx, indicators_params_xlsx
from tests.workflows.conftest import ENTITY


def _create_run(db, snapshot, workflow, entity, **over):
    kw = dict(
        workflow_id=workflow.id,
        snapshot_id=snapshot.id,
        reference_date=date(2025, 12, 31),
        entity_id=entity.id,
    )
    kw.update(over)
    return service.create_run(db, **kw)


def _attach_facts(db, run_id, data):
    service.attach_fact_file(db, run_id=run_id, filename="facts.xlsx", data=data)


def _package_member(db, run_id, suffix) -> str:
    out = next(
        f
        for f in service.run_files(db, run_id)
        if f.role is RunFileRole.package_output
    )
    zf = zipfile.ZipFile(get_settings().data_dir / out.storage_key)
    name = next(n for n in zf.namelist() if n.endswith(suffix))
    return zf.read(name).decode()


def test_full_run_derived_is_clean(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
    demo_fact_xlsx: bytes,
) -> None:
    """One fact file, no indicators upload → derived, clean, generated."""
    run = _create_run(db_session, ready_snapshot, lcr_workflow, entity)
    assert run.status is RunStatus.created
    assert run.entity_lei == ENTITY
    assert run.country == "GB" and run.base_currency == "EUR"

    _attach_facts(db_session, run.id, demo_fact_xlsx)
    run = service.execute_run(db_session, run.id)
    assert run.status is RunStatus.generated, run.error

    findings = service.list_findings(db_session, run.id)
    assert not [f for f in findings if f.severity is Severity.error]
    assert [f.code for f in findings if f.severity is Severity.info] == [
        "ENTRY_POINT_UNVERIFIED"
    ]
    files = service.run_files(db_session, run.id)
    assert any(f.role is RunFileRole.validation_report for f in files)
    # No indicators/params file was uploaded.
    assert not any(f.role is RunFileRole.indicators_params for f in files)


def test_derived_indicators_and_parameters(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
    demo_fact_xlsx: bytes,
) -> None:
    run = _create_run(db_session, ready_snapshot, lcr_workflow, entity)
    _attach_facts(db_session, run.id, demo_fact_xlsx)
    service.execute_run(db_session, run.id)

    indicators = _package_member(db_session, run.id, "FilingIndicators.csv")
    # Facts present -> true; other module templates -> false (incl. open C_77.00).
    assert "C_67.00.a,true" in indicators
    assert "C_72.00.a,false" in indicators
    assert "C_77.00,false" in indicators

    params = _package_member(db_session, run.id, "parameters.csv")
    assert "entityID,rs:5299001234567890ABCD.CON" in params
    assert "refPeriod,2025-12-31" in params
    assert "baseCurrency,iso4217:EUR" in params


def test_indicators_override_is_used(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
    demo_fact_xlsx: bytes,
) -> None:
    """An uploaded indicators file overrides derivation (advanced)."""
    run = _create_run(db_session, ready_snapshot, lcr_workflow, entity)
    _attach_facts(db_session, run.id, demo_fact_xlsx)
    # Override declares C_72.00.a reported although it has no facts.
    override = indicators_params_xlsx(
        [
            ("entity_lei", ENTITY),
            ("reference_date", "2025-12-31"),
            ("base_currency", "EUR"),
            ("decimals", -3),
        ],
        [("C_67.00.a", True), ("C_72.00.a", True)],
    )
    service.attach_indicators_params_file(
        db_session, run_id=run.id, filename="ip.xlsx", data=override
    )
    run = service.execute_run(db_session, run.id)
    # The override's empty C_72.00.a indicator surfaces (derivation wouldn't).
    codes = [f.code for f in service.list_findings(db_session, run.id)]
    assert "EMPTY_FILING_INDICATOR" in codes
    assert run.status is RunStatus.generated  # warning only


def test_open_table_guard(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
) -> None:
    run = _create_run(db_session, ready_snapshot, lcr_workflow, entity)
    data = fact_xlsx(
        [
            ("C_67.00.a", "0020", "0060", 100000),  # closed, resolves
            ("C_77.00", "0010", "0010", 5),  # open/keyed -> guarded
        ]
    )
    _attach_facts(db_session, run.id, data)
    run = service.execute_run(db_session, run.id)
    assert run.status is RunStatus.failed_validation
    findings = service.list_findings(db_session, run.id)
    open_f = [f for f in findings if f.code == "OPEN_TABLE_UNSUPPORTED"]
    assert open_f and open_f[0].template_code == "C_77.00"
    # The open table produced no CSV, but the closed one did.
    names = zipfile.ZipFile(
        get_settings().data_dir
        / next(
            f
            for f in service.run_files(db_session, run.id)
            if f.role is RunFileRole.package_output
        ).storage_key
    ).namelist()
    assert any(n.endswith("c_67.00.a.csv") for n in names)
    assert not any(n.endswith("c_77.00.csv") for n in names)


def test_unresolvable_fact_fails_validation(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
) -> None:
    run = _create_run(db_session, ready_snapshot, lcr_workflow, entity)
    _attach_facts(db_session, run.id, fact_xlsx([("C_67.00.a", "9999", "9999", 1)]))
    run = service.execute_run(db_session, run.id)
    assert run.status is RunStatus.failed_validation
    findings = service.list_findings(db_session, run.id)
    assert any(f.code == "UNRESOLVED_FACT" and f.row_code == "9999" for f in findings)
    files = service.run_files(db_session, run.id)
    assert any(f.role is RunFileRole.package_output for f in files)


def test_execute_without_fact_file_rejected(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
) -> None:
    run = _create_run(db_session, ready_snapshot, lcr_workflow, entity)
    with pytest.raises(ValidationError, match="no fact file"):
        service.execute_run(db_session, run.id)


def test_create_run_rejects_non_ready_snapshot(
    db_session: Session, lcr_workflow: WorkflowConfig, entity: Entity
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
        _create_run(db_session, snap, lcr_workflow, entity)


def test_create_run_rejects_module_not_in_snapshot(
    db_session: Session, ready_snapshot: TaxonomySnapshot, entity: Entity
) -> None:
    wf = WorkflowConfig(
        name="COREP — Own Funds", framework_code="COREP", module_code="COREP_OF"
    )
    db_session.add(wf)
    db_session.commit()
    with pytest.raises(ValidationError, match="not in snapshot"):
        _create_run(db_session, ready_snapshot, wf, entity)


def test_seed_is_idempotent(db_session: Session) -> None:
    assert seed_workflow_configs(db_session) == 20
    assert seed_workflow_configs(db_session) == 0
    assert seed_entities(db_session) == 3
    assert seed_entities(db_session) == 0
