"""Run deletion is blocked mid-execution, and the formula task is delete-safe."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ConflictError
from app.facts.models import Fact, RunFile
from app.taxonomy.models import TaxonomySnapshot
from app.validation.models import ValidationFinding
from app.workflows import service
from app.workflows.models import Entity, Run, RunStatus, WorkflowConfig


def _run(db, snap, wf, ent) -> Run:
    return service.create_run(
        db,
        workflow_id=wf.id,
        snapshot_id=snap.id,
        reference_date=date(2025, 12, 31),
        entity_id=ent.id,
    )


@pytest.mark.parametrize(
    "status", [RunStatus.running, RunStatus.formula_validation_running]
)
def test_cannot_delete_run_in_progress(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
    status: RunStatus,
) -> None:
    run = _run(db_session, ready_snapshot, lcr_workflow, entity)
    run.status = status
    db_session.commit()

    with pytest.raises(ConflictError, match="still running"):
        service.delete_run(db_session, run.id)
    assert db_session.get(Run, run.id) is not None  # not deleted


def test_can_delete_finished_run(
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
    service.execute_run(db_session, run.id)  # finishes (generated / failed_*)
    assert run.status not in (
        RunStatus.running, RunStatus.formula_validation_running
    )
    service.delete_run(db_session, run.id)
    assert db_session.get(Run, run.id) is None


def test_formula_task_discards_when_run_deleted_midway(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
    demo_fact_xlsx: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the run vanishes during the (long) Arelle call, the task writes nothing
    back and does not resurrect it — the status re-check closes the race."""
    # The background task opens its own SessionLocal; bind it to the test engine.
    factory = sessionmaker(bind=db_session.get_bind(), autoflush=False)
    monkeypatch.setattr(service, "SessionLocal", factory)

    run = _run(db_session, ready_snapshot, lcr_workflow, entity)
    service.attach_fact_file(
        db_session, run_id=run.id, filename="facts.xlsx", data=demo_fact_xlsx
    )
    service.execute_run(db_session, run.id)  # produces a package_output
    run_id = run.id
    run.status = RunStatus.formula_validation_running
    db_session.commit()

    # A validator whose "run" deletes the row mid-window (a concurrent removal).
    class _DeletingValidator:
        def __init__(self, **_kw):
            pass

        def validate_detailed(self, _path, _taxo):
            with factory() as d:
                d.execute(delete(Fact).where(Fact.run_id == run_id))
                d.execute(
                    delete(ValidationFinding).where(
                        ValidationFinding.run_id == run_id
                    )
                )
                d.execute(delete(RunFile).where(RunFile.run_id == run_id))
                d.execute(delete(Run).where(Run.id == run_id))
                d.commit()
            return None  # the task returns before using this

    monkeypatch.setattr(service, "ArelleFormulaValidator", _DeletingValidator)

    # Must not raise, must not write findings, must not resurrect the run.
    service.run_formula_validation_task(run_id)

    db_session.expire_all()
    assert db_session.get(Run, run_id) is None
    assert (
        db_session.query(ValidationFinding).filter_by(run_id=run_id).count() == 0
    )
