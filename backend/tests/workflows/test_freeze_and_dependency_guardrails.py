"""Freeze + dependency-change guardrails (audit findings B1, C1, C2).

B1 — entity values (incl. name) are frozen on the run at execution; a later
     rename never alters a historical run.
C1 — a new execution detects a changed entity and stops for confirmation.
C2 — a new execution detects a replaced release artifact and stops for
     confirmation.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.errors import DependencyChangedError
from app.taxonomy.models import TaxonomySnapshot
from app.workflows import service
from app.workflows.models import Entity, WorkflowConfig
from app.workflows.schemas import RunOut


def _run(db, snap, wf, ent) -> service.Run:
    return service.create_run(
        db,
        workflow_id=wf.id,
        snapshot_id=snap.id,
        reference_date=date(2025, 12, 31),
        entity_id=ent.id,
    )


# --- B1: entity values frozen ---------------------------------------------


def test_entity_values_frozen_on_run(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
) -> None:
    run = _run(db_session, ready_snapshot, lcr_workflow, entity)
    assert run.entity_name == entity.name
    assert run.entity_lei == entity.lei
    assert run.entity_scope == entity.default_scope.upper()
    assert run.country == entity.country.upper()
    # The frozen name is exposed on the API shape (was absent before the fix).
    assert RunOut.model_validate(run).entity_name == entity.name


def test_rename_does_not_change_historical_run(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
) -> None:
    run = _run(db_session, ready_snapshot, lcr_workflow, entity)
    original = entity.name

    entity.name = "Meridian Group Holdings II plc"
    db_session.commit()
    db_session.refresh(run)

    # Frozen — the run and its report header still show the execution-time name.
    assert run.entity_name == original
    pairs = dict(service._report_identity(db_session, run, lcr_workflow, "p.zip"))
    assert pairs["Entity"].startswith(original)
    assert "II plc" not in pairs["Entity"]


# --- C1: entity change requires confirmation -------------------------------


def test_no_change_reexecutes_without_acknowledge(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
) -> None:
    run = _run(db_session, ready_snapshot, lcr_workflow, entity)
    assert service.detect_dependency_changes(db_session, run) == []
    new = service.reexecute_run(db_session, run.id)
    assert new.id != run.id
    assert new.entity_name == run.entity_name


def test_entity_change_requires_confirmation(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
) -> None:
    run = _run(db_session, ready_snapshot, lcr_workflow, entity)

    entity.country = "FR"
    db_session.commit()

    changes = service.detect_dependency_changes(db_session, run)
    assert [c["kind"] for c in changes] == ["entity_changed"]
    assert "country" in changes[0]["message"]

    # Unacknowledged: stops, carrying the change list — never silently re-binds.
    with pytest.raises(DependencyChangedError) as ei:
        service.reexecute_run(db_session, run.id)
    assert any("country" in c["message"] for c in ei.value.details)

    # Acknowledged: proceeds, using the current value.
    new = service.reexecute_run(db_session, run.id, acknowledge_changes=True)
    assert new.id != run.id
    assert new.country == "FR"


def test_entity_deleted_is_detected(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
) -> None:
    run = _run(db_session, ready_snapshot, lcr_workflow, entity)
    db_session.delete(entity)
    db_session.commit()

    changes = service.detect_dependency_changes(db_session, run)
    assert any(c["kind"] == "entity_deleted" for c in changes)
    with pytest.raises(DependencyChangedError):
        service.reexecute_run(db_session, run.id)


# --- C2: replaced release artifact requires confirmation -------------------


def test_release_change_requires_confirmation(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
) -> None:
    run = _run(db_session, ready_snapshot, lcr_workflow, entity)

    # Simulate replacing the DPM artifact: its checksum changes, so the release
    # fingerprint changes. (verify_snapshot only checks file presence, so the
    # release stays 'ready'.)
    ready_snapshot.checksum = "f" * 64
    db_session.commit()

    changes = service.detect_dependency_changes(db_session, run)
    assert [c["kind"] for c in changes] == ["release_changed"]

    with pytest.raises(DependencyChangedError):
        service.reexecute_run(db_session, run.id)

    new = service.reexecute_run(db_session, run.id, acknowledge_changes=True)
    assert new.id != run.id
    assert new.release_fingerprint != run.release_fingerprint


# --- API wiring ------------------------------------------------------------


def test_reexecute_endpoint_409_then_acknowledge(
    client: TestClient,
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
) -> None:
    run = _run(db_session, ready_snapshot, lcr_workflow, entity)
    entity.name = "Renamed Bank plc"
    db_session.commit()

    r = client.post(f"/api/workflows/runs/{run.id}/reexecute")
    assert r.status_code == 409
    body = r.json()["error"]
    assert body["code"] == "dependency_changed"
    assert any(c["kind"] == "entity_changed" for c in body["details"])

    r = client.post(
        f"/api/workflows/runs/{run.id}/reexecute",
        json={"acknowledge_changes": True},
    )
    assert r.status_code == 201
    assert r.json()["id"] != run.id
