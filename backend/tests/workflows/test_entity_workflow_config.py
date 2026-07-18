"""Per-(entity, workflow) config: Auto/True/False declarations + param overrides."""

from __future__ import annotations

import zipfile
from datetime import date

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.facts.models import RunFileRole
from app.taxonomy.models import TaxonomySnapshot
from app.validation.models import Severity
from app.workflows import service
from app.workflows.models import Entity, RunStatus, WorkflowConfig


def _create_run(db, snapshot, workflow, entity, **over):
    kw = dict(
        workflow_id=workflow.id,
        snapshot_id=snapshot.id,
        reference_date=date(2025, 12, 31),
        entity_id=entity.id,
    )
    kw.update(over)
    return service.create_run(db, **kw)


def _indicators(db, run_id) -> str:
    out = next(
        f
        for f in service.run_files(db, run_id)
        if f.role is RunFileRole.package_output
    )
    zf = zipfile.ZipFile(get_settings().data_dir / out.storage_key)
    name = next(n for n in zf.namelist() if n.endswith("FilingIndicators.csv"))
    return zf.read(name).decode()


def _package_names(db, run_id) -> list[str]:
    out = next(
        f
        for f in service.run_files(db, run_id)
        if f.role is RunFileRole.package_output
    )
    return zipfile.ZipFile(get_settings().data_dir / out.storage_key).namelist()


# --- pure derivation semantics --------------------------------------------


def test_resolve_declaration_three_states() -> None:
    closed = {"C_67.00.a"}
    # Auto: reported iff facts.
    assert service._resolve_declaration("C_67.00.a", {}, closed) is True
    assert service._resolve_declaration("C_72.00.a", {}, closed) is False
    # True: forced positive even without facts.
    assert (
        service._resolve_declaration("C_72.00.a", {"C_72.00.a": "true"}, closed)
        is True
    )
    # False: forced negative even with facts.
    assert (
        service._resolve_declaration("C_67.00.a", {"C_67.00.a": "false"}, closed)
        is False
    )


def test_clean_declarations_normalises_and_drops_auto() -> None:
    cleaned = service._clean_declarations(
        {
            "C 67.00.a": "true",  # EBA display form -> canonical
            "C_72.00.a": "auto",  # dropped (Auto is the default)
            "C_73.00.a": "false",
            "junk": "true",  # unparseable code -> dropped
            "C_74.00.a": "maybe",  # invalid value -> dropped
        }
    )
    # Declarations are stored at template level (table variants collapsed).
    assert cleaned == {"C_67.00": "true", "C_73.00": "false"}


# --- end-to-end through execute_run ---------------------------------------


def test_true_forces_positive_indicator(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
    demo_fact_xlsx: bytes,
) -> None:
    service.upsert_entity_workflow_config(
        db_session,
        entity_id=entity.id,
        workflow_id=lcr_workflow.id,
        indicator_declarations={"C_72.00.a": "true"},  # no facts for it
        base_currency=None,
        decimals=None,
    )
    run = _create_run(db_session, ready_snapshot, lcr_workflow, entity)
    service.attach_fact_file(
        db_session, run_id=run.id, filename="f.xlsx", data=demo_fact_xlsx
    )
    run = service.execute_run(db_session, run.id)

    assert "C_72.00,true" in _indicators(db_session, run.id)
    codes = [f.code for f in service.list_findings(db_session, run.id)]
    # Reported but no facts -> warning, not an error; run still generated.
    assert "EMPTY_FILING_INDICATOR" in codes
    assert run.status is RunStatus.generated, run.error


def test_false_declares_not_filed_and_excludes_facts(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
    demo_fact_xlsx: bytes,  # 2 facts for C_67.00.a
) -> None:
    service.upsert_entity_workflow_config(
        db_session,
        entity_id=entity.id,
        workflow_id=lcr_workflow.id,
        indicator_declarations={"C_67.00.a": "false"},
        base_currency=None,
        decimals=None,
    )
    run = _create_run(db_session, ready_snapshot, lcr_workflow, entity)
    service.attach_fact_file(
        db_session, run_id=run.id, filename="f.xlsx", data=demo_fact_xlsx
    )
    run = service.execute_run(db_session, run.id)

    # Indicator forced negative; the excluded template produces no CSV.
    assert "C_67.00,false" in _indicators(db_session, run.id)
    names = _package_names(db_session, run.id)
    assert not any(n.endswith("c_67.00.a.csv") for n in names)

    findings = service.list_findings(db_session, run.id)
    not_filed = [f for f in findings if f.code == "TEMPLATE_DECLARED_NOT_FILED"]
    assert len(not_filed) == 1
    assert not_filed[0].severity is Severity.warning
    assert not_filed[0].message == (
        "template C_67.00 declared not-filed; 2 facts excluded"
    )
    # No missing-indicator error even though facts existed for the template.
    assert not any(f.code == "MISSING_FILING_INDICATOR" for f in findings)
    assert run.status is RunStatus.generated, run.error


def test_auto_is_unchanged_default(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
    demo_fact_xlsx: bytes,
) -> None:
    # An empty config = every template Auto = the pre-config behaviour.
    service.upsert_entity_workflow_config(
        db_session,
        entity_id=entity.id,
        workflow_id=lcr_workflow.id,
        indicator_declarations={},
        base_currency=None,
        decimals=None,
    )
    run = _create_run(db_session, ready_snapshot, lcr_workflow, entity)
    service.attach_fact_file(
        db_session, run_id=run.id, filename="f.xlsx", data=demo_fact_xlsx
    )
    run = service.execute_run(db_session, run.id)
    indicators = _indicators(db_session, run.id)
    assert "C_67.00,true" in indicators  # has facts
    assert "C_72.00,false" in indicators  # no facts
    assert run.status is RunStatus.generated, run.error


def test_param_overrides_seed_run_defaults(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
) -> None:
    service.upsert_entity_workflow_config(
        db_session,
        entity_id=entity.id,
        workflow_id=lcr_workflow.id,
        indicator_declarations={},
        base_currency="usd",
        decimals=-2,
    )
    # Caller doesn't specify currency/decimals -> config supplies the defaults.
    run = _create_run(db_session, ready_snapshot, lcr_workflow, entity)
    assert run.base_currency == "USD"
    assert run.decimals == -2

    # An explicit value on the run still wins over the config.
    run2 = _create_run(
        db_session, ready_snapshot, lcr_workflow, entity, base_currency="GBP"
    )
    assert run2.base_currency == "GBP"


# --- endpoints -------------------------------------------------------------


def test_config_get_update_roundtrip(client, db_session, entity, lcr_workflow) -> None:
    url = f"/api/workflows/entities/{entity.id}/configs/{lcr_workflow.id}"
    # Unset config returns the Auto default (empty map).
    got = client.get(url)
    assert got.status_code == 200
    assert got.json()["indicator_declarations"] == {}

    put = client.put(
        url,
        json={
            "indicator_declarations": {"C 67.00.a": "false", "C_72.00.a": "auto"},
            "base_currency": "usd",
            "decimals": -2,
        },
    )
    assert put.status_code == 200
    body = put.json()
    # Canonicalised + Auto dropped.
    assert body["indicator_declarations"] == {"C_67.00": "false"}
    assert body["base_currency"] == "USD"
    assert body["decimals"] == -2


def test_entity_create_and_edit(client) -> None:
    created = client.post(
        "/api/workflows/entities",
        json={
            "name": "Test Bank plc",
            "lei": "213800TESTBANK000001",
            "country": "gb",
            "default_scope": "con",
        },
    )
    assert created.status_code == 201, created.text
    eid = created.json()["id"]
    assert created.json()["country"] == "GB"
    assert created.json()["default_scope"] == "CON"

    edited = client.put(
        f"/api/workflows/entities/{eid}",
        json={
            "name": "Test Bank plc (renamed)",
            "lei": "213800TESTBANK000001",
            "country": "DE",
            "default_scope": "IND",
        },
    )
    assert edited.status_code == 200
    assert edited.json()["name"] == "Test Bank plc (renamed)"
    assert edited.json()["country"] == "DE"


def test_entity_create_rejects_duplicate_lei(client) -> None:
    body = {
        "name": "Dup",
        "lei": "213800DUPDUPDUP00001",
        "country": "GB",
        "default_scope": "IND",
    }
    assert client.post("/api/workflows/entities", json=body).status_code == 201
    dup = client.post("/api/workflows/entities", json=body)
    assert dup.status_code == 409
