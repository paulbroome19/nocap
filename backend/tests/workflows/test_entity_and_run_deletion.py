"""Entities and runs are freely deletable (audit findings D1, B2)."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.facts.models import Fact, RunFile
from app.taxonomy.models import TaxonomySnapshot
from app.validation.models import ValidationFinding
from app.workflows import service
from app.workflows.models import Entity, EntityWorkflowConfig, Run, WorkflowConfig


def _run(db, snap, wf, ent) -> Run:
    return service.create_run(
        db,
        workflow_id=wf.id,
        snapshot_id=snap.id,
        reference_date=date(2025, 12, 31),
        entity_id=ent.id,
    )


# --- D1: entity deletion ---------------------------------------------------


def test_delete_entity_leaves_runs_frozen(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
) -> None:
    # A config for the entity, and a run that froze its values.
    service.upsert_entity_workflow_config(
        db_session, entity_id=entity.id, workflow_id=lcr_workflow.id,
        indicator_declarations={}, base_currency="EUR", decimals=-3,
    )
    run = _run(db_session, ready_snapshot, lcr_workflow, entity)
    frozen_name, frozen_lei, ent_id = run.entity_name, run.entity_lei, entity.id

    service.delete_entity(db_session, ent_id)

    # Entity and its config are gone.
    assert db_session.get(Entity, ent_id) is None
    assert (
        db_session.query(EntityWorkflowConfig).filter_by(entity_id=ent_id).count()
        == 0
    )
    # The run is untouched: frozen values kept, id retained as provenance.
    db_session.expire_all()
    kept = db_session.get(Run, run.id)
    assert kept is not None
    assert kept.entity_name == frozen_name
    assert kept.entity_lei == frozen_lei
    assert kept.entity_id == ent_id  # dangling provenance (no FK cascade)


def test_delete_entity_endpoint(
    client: TestClient, db_session: Session, entity: Entity
) -> None:
    assert client.delete(f"/api/workflows/entities/{entity.id}").status_code == 204
    assert client.get(f"/api/workflows/entities/{entity.id}").status_code == 404


def test_delete_unknown_entity_404(db_session: Session) -> None:
    with pytest.raises(NotFoundError):
        service.delete_entity(db_session, 999999)


# --- B2: run deletion ------------------------------------------------------


def test_delete_run_removes_everything(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
    demo_fact_xlsx: bytes,
) -> None:
    run = _run(db_session, ready_snapshot, lcr_workflow, entity)
    service.attach_fact_file(
        db_session, run_id=run.id, filename="facts.xlsx", data=demo_fact_xlsx
    )
    service.execute_run(db_session, run.id)

    run_dir = get_settings().data_dir / "runs" / str(run.id)
    assert run_dir.exists()
    assert db_session.query(RunFile).filter_by(run_id=run.id).count() > 0
    assert db_session.query(Fact).filter_by(run_id=run.id).count() > 0
    assert db_session.query(ValidationFinding).filter_by(run_id=run.id).count() > 0

    service.delete_run(db_session, run.id)

    assert db_session.get(Run, run.id) is None
    assert db_session.query(RunFile).filter_by(run_id=run.id).count() == 0
    assert db_session.query(Fact).filter_by(run_id=run.id).count() == 0
    assert db_session.query(ValidationFinding).filter_by(run_id=run.id).count() == 0
    assert not run_dir.exists()


def test_delete_run_leaves_sibling_executions(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
) -> None:
    first = _run(db_session, ready_snapshot, lcr_workflow, entity)
    second = service.reexecute_run(db_session, first.id)  # same instance

    service.delete_run(db_session, first.id)

    assert db_session.get(Run, first.id) is None
    assert db_session.get(Run, second.id) is not None  # sibling untouched


def test_delete_run_endpoint(
    client: TestClient,
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
) -> None:
    run = _run(db_session, ready_snapshot, lcr_workflow, entity)
    assert client.delete(f"/api/workflows/runs/{run.id}").status_code == 204
    assert client.get(f"/api/workflows/runs/{run.id}").status_code == 404


def test_delete_unknown_run_404(db_session: Session) -> None:
    with pytest.raises(NotFoundError):
        service.delete_run(db_session, 999999)
