"""Re-executing when a dependency is gone requires reselection (C3, C4, C5)."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.core.errors import DependencyChangedError
from app.taxonomy import service as taxonomy
from app.taxonomy.models import SnapshotStatus, TaxonomySnapshot
from app.workflows import service
from app.workflows.models import Entity, WorkflowConfig


def _run(db, snap, wf, ent):
    return service.create_run(
        db,
        workflow_id=wf.id,
        snapshot_id=snap.id,
        reference_date=date(2025, 12, 31),
        entity_id=ent.id,
    )


def _ready_snapshot(db, mini_dpm: Path, label: str) -> TaxonomySnapshot:
    snap = taxonomy.register_snapshot(
        db, file_bytes=f"accdb-{label}".encode(), filename="DPM.accdb",
        version_label=label,
    )

    def stub(src, out, *, settings, tables=None):
        shutil.copyfile(mini_dpm, out)

    taxonomy.ingest_snapshot(db, snap, converter=stub)
    assert snap.status is SnapshotStatus.ready
    return snap


def _other_entity(db) -> Entity:
    return service.create_entity(
        db, name="Northwind Bank plc", lei="529900OTHERENTITY002",
        country="FR", default_scope="IND",
    )


# --- C4: entity deleted → reselect -----------------------------------------


def test_deleted_entity_requires_reselection(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
) -> None:
    run = _run(db_session, ready_snapshot, lcr_workflow, entity)
    service.delete_entity(db_session, entity.id)

    # Bare acknowledge is NOT enough for a vanished entity — must reselect.
    with pytest.raises(DependencyChangedError) as ei:
        service.reexecute_run(db_session, run.id, acknowledge_changes=True)
    kinds = [c["kind"] for c in ei.value.details]
    assert "entity_deleted" in kinds
    assert any("Select a current entity" in c["message"] for c in ei.value.details)

    # Choosing a current entity resolves it and proceeds with that entity.
    replacement = _other_entity(db_session)
    new = service.reexecute_run(db_session, run.id, entity_id=replacement.id)
    assert new.id != run.id
    assert new.entity_id == replacement.id
    assert new.entity_lei == replacement.lei


# --- C5: release deleted → reselect ----------------------------------------


def test_deleted_release_requires_reselection(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
    mini_dpm: Path,
) -> None:
    run = _run(db_session, ready_snapshot, lcr_workflow, entity)
    replacement = _ready_snapshot(db_session, mini_dpm, "3.0")

    # Delete the release the run used (allowed since PR #45).
    taxonomy.delete_release(db_session, ready_snapshot)

    with pytest.raises(DependencyChangedError) as ei:
        service.reexecute_run(db_session, run.id, acknowledge_changes=True)
    kinds = [c["kind"] for c in ei.value.details]
    assert "release_deleted" in kinds
    assert any("Select a release" in c["message"] for c in ei.value.details)

    # Choosing a current release resolves it and binds the new run to it.
    new = service.reexecute_run(
        db_session, run.id, release_snapshot_id=replacement.id
    )
    assert new.id != run.id
    assert new.snapshot_id == replacement.id


# --- changed-but-usable still acknowledges (unchanged from #44) -------------


def test_changed_entity_still_acknowledges(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
) -> None:
    run = _run(db_session, ready_snapshot, lcr_workflow, entity)
    entity.country = "FR"  # a change, but the entity still exists
    db_session.commit()

    with pytest.raises(DependencyChangedError):
        service.reexecute_run(db_session, run.id)
    # A still-usable change may be acknowledged (proceed with current values).
    new = service.reexecute_run(db_session, run.id, acknowledge_changes=True)
    assert new.country == "FR"


def test_no_change_reexecutes_plainly(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
) -> None:
    run = _run(db_session, ready_snapshot, lcr_workflow, entity)
    new = service.reexecute_run(db_session, run.id)
    assert new.id != run.id
