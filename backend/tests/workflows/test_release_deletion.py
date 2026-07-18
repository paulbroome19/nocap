"""Release deletion is guarded by the runs that reference it (end to end)."""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.taxonomy.models import TaxonomySnapshot
from app.workflows import service
from app.workflows.models import Entity, WorkflowConfig


def test_count_runs_for_snapshot(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
) -> None:
    assert service.count_runs_for_snapshot(db_session, ready_snapshot.id) == 0
    service.create_run(
        db_session,
        workflow_id=lcr_workflow.id,
        snapshot_id=ready_snapshot.id,
        reference_date=date(2025, 12, 31),
        entity_id=entity.id,
    )
    assert service.count_runs_for_snapshot(db_session, ready_snapshot.id) == 1


def test_delete_endpoint_blocked_when_runs_exist(
    client: TestClient,
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
) -> None:
    service.create_run(
        db_session,
        workflow_id=lcr_workflow.id,
        snapshot_id=ready_snapshot.id,
        reference_date=date(2025, 12, 31),
        entity_id=entity.id,
    )
    resp = client.delete(f"/api/taxonomy/snapshots/{ready_snapshot.id}")
    assert resp.status_code == 409
    assert "cannot be deleted" in resp.json()["error"]["message"]
    # The release is still present.
    assert client.get(
        f"/api/taxonomy/snapshots/{ready_snapshot.id}"
    ).status_code == 200
