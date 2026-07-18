"""Run instance keys (snapshot/adjusted/version) + scope-taken-from-entity."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.taxonomy.models import TaxonomySnapshot
from app.workflows import service
from app.workflows.models import Entity, WorkflowConfig


def test_instance_keys_and_scope_from_entity(
    db_session: Session,
    client,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,  # default_scope = CON
) -> None:
    run = service.create_run(
        db_session,
        workflow_id=lcr_workflow.id,
        snapshot_id=ready_snapshot.id,
        reference_date=date(2025, 12, 31),
        entity_id=entity.id,
        snapshot_key="EOD-2025-12-31",
        adjusted_key="ADJ-1",
        version_key="v2",
    )
    assert (run.snapshot_key, run.adjusted_key, run.version_key) == (
        "EOD-2025-12-31", "ADJ-1", "v2",
    )
    # Scope comes from the entity record, not any per-run input.
    assert run.entity_scope == entity.default_scope == "CON"

    # Keys surface in detail and history.
    detail = client.get(f"/api/workflows/runs/{run.id}").json()["run"]
    assert detail["snapshot_key"] == "EOD-2025-12-31"
    assert detail["version_key"] == "v2"
    assert detail["entity_scope"] == "CON"

    history = client.get(
        f"/api/workflows/configs/{lcr_workflow.id}/runs"
    ).json()
    assert history[0]["adjusted_key"] == "ADJ-1"


def test_blank_keys_stored_as_null(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
) -> None:
    run = service.create_run(
        db_session,
        workflow_id=lcr_workflow.id,
        snapshot_id=ready_snapshot.id,
        reference_date=date(2025, 12, 31),
        entity_id=entity.id,
        snapshot_key="   ",
    )
    assert run.snapshot_key is None
    assert run.adjusted_key is None
    assert run.version_key is None


def test_create_run_api_no_scope_input(
    client,
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
) -> None:
    resp = client.post(
        "/api/workflows/runs",
        json={
            "workflow_id": lcr_workflow.id,
            "snapshot_id": ready_snapshot.id,
            "reference_date": "2025-12-31",
            "entity_id": entity.id,
            "snapshot_key": "K1",
            "version_key": "V1",
            # A stray scope is ignored — scope is entity-owned now.
            "scope": "IND",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["snapshot_key"] == "K1" and body["version_key"] == "V1"
    assert body["entity_scope"] == "CON"  # entity default, not the stray "IND"


def test_suite_summary_reports_last_run(
    client,
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,  # category=Liquidity
    entity: Entity,
) -> None:
    run = service.create_run(
        db_session,
        workflow_id=lcr_workflow.id,
        snapshot_id=ready_snapshot.id,
        reference_date=date(2025, 12, 31),
        entity_id=entity.id,
    )
    suites = client.get(
        "/api/workflows/categories/Liquidity/suites"
    ).json()
    lcr = next(s for s in suites if s["module_code"] == "COREP_LCR_DA")
    assert lcr["last_run"]["id"] == run.id
    assert lcr["last_run"]["reference_date"] == "2025-12-31"

    cats = {c["category"]: c for c in client.get("/api/workflows/categories").json()}
    assert cats["Liquidity"]["last_run"]["id"] == run.id
