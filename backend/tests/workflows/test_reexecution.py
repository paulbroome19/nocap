"""Re-execution / resubmission: a new run for the same instance identity."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.taxonomy.models import TaxonomySnapshot
from app.workflows import service
from app.workflows.models import Entity, RunStatus, WorkflowConfig


def _create(db, snapshot, workflow, entity, **over):
    kw = dict(
        workflow_id=workflow.id,
        snapshot_id=snapshot.id,
        reference_date=date(2025, 12, 31),
        entity_id=entity.id,
        snapshot_key="S1",
        adjusted_key="A1",
        version_key="V1",
    )
    kw.update(over)
    return service.create_run(db, **kw)


def test_reexecute_clones_instance_identity_append_only(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
) -> None:
    original = _create(db_session, ready_snapshot, lcr_workflow, entity)
    resubmission = service.reexecute_run(db_session, original.id)

    # A new, distinct run record (append-only) …
    assert resubmission.id != original.id
    assert resubmission.status is RunStatus.created
    # … sharing the full instance identity.
    assert service.instance_identity(resubmission) == service.instance_identity(
        original
    )
    assert (resubmission.entity_id, resubmission.reference_date) == (
        original.entity_id, original.reference_date,
    )
    assert (
        resubmission.snapshot_key,
        resubmission.adjusted_key,
        resubmission.version_key,
    ) == ("S1", "A1", "V1")
    # Both executions remain in history.
    hist = service.list_runs(db_session, lcr_workflow.id)
    assert {original.id, resubmission.id} <= {r.id for r in hist}


def test_reexecute_preserves_release_and_parameters(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
) -> None:
    original = _create(
        db_session, ready_snapshot, lcr_workflow, entity,
        base_currency="USD", decimals=-2,
    )
    resub = service.reexecute_run(db_session, original.id)
    assert resub.release_id == original.release_id
    assert (resub.base_currency, resub.decimals) == ("USD", -2)


def test_reexecute_endpoint(
    client, db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
) -> None:
    original = _create(db_session, ready_snapshot, lcr_workflow, entity)
    resp = client.post(f"/api/workflows/runs/{original.id}/reexecute")
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] != original.id
    assert body["status"] == "created"
    assert body["snapshot_key"] == "S1"
