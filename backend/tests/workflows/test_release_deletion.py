"""Release deletion is allowed regardless of runs (A2); history stays frozen."""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.taxonomy.models import TaxonomySnapshot
from app.workflows import service
from app.workflows.models import Entity, Run, WorkflowConfig


def _run(db, snap, wf, ent) -> Run:
    return service.create_run(
        db,
        workflow_id=wf.id,
        snapshot_id=snap.id,
        reference_date=date(2025, 12, 31),
        entity_id=ent.id,
    )


def test_delete_allowed_when_runs_exist(
    client: TestClient,
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
) -> None:
    run = _run(db_session, ready_snapshot, lcr_workflow, entity)
    snap_id = ready_snapshot.id

    # Deletion is permitted even though a run references the release.
    resp = client.delete(f"/api/taxonomy/snapshots/{snap_id}")
    assert resp.status_code == 204
    assert client.get(f"/api/taxonomy/snapshots/{snap_id}").status_code == 404

    # The run is untouched — its frozen provenance and values remain.
    db_session.expire_all()
    kept = db_session.get(Run, run.id)
    assert kept is not None
    assert kept.snapshot_id == snap_id  # frozen id retained (no FK cascade)
    assert kept.entity_lei == entity.lei
