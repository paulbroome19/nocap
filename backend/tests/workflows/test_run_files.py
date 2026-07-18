"""Run-file download: stable ids across rewrites, disk reconciliation, 410."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.facts import service as facts
from app.facts.models import RunFileRole
from app.taxonomy.models import TaxonomySnapshot
from app.workflows import service
from app.workflows.models import Entity, WorkflowConfig


def test_upsert_run_file_keeps_stable_id(db_session: Session) -> None:
    settings = get_settings()
    first = facts.store_run_file(
        db_session, run_id=1, role=RunFileRole.validation_report,
        filename="validation_report_run1.txt", data=b"v1", settings=settings,
    )
    db_session.commit()
    fid, key = first.id, first.storage_key

    # Rewriting (as the formula phase does) must reuse the row, not churn the id.
    second = facts.upsert_run_file(
        db_session, run_id=1, role=RunFileRole.validation_report,
        filename="validation_report_run1.txt", data=b"v2-longer",
        settings=settings,
    )
    db_session.commit()
    assert second.id == fid
    assert second.storage_key == key
    assert (settings.data_dir / key).read_bytes() == b"v2-longer"
    reports = [
        f
        for f in facts.list_run_files(db_session, 1)
        if f.role is RunFileRole.validation_report
    ]
    assert len(reports) == 1  # not accumulated


def test_upsert_creates_when_absent(db_session: Session) -> None:
    settings = get_settings()
    rf = facts.upsert_run_file(
        db_session, run_id=2, role=RunFileRole.validation_report,
        filename="validation_report_run2.txt", data=b"x", settings=settings,
    )
    db_session.commit()
    assert rf.id is not None
    assert facts.run_file_present(settings, rf)


def test_downloads_work_and_missing_is_surfaced(
    client,
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
    demo_fact_xlsx: bytes,
) -> None:
    run = service.create_run(
        db_session,
        workflow_id=lcr_workflow.id,
        snapshot_id=ready_snapshot.id,
        reference_date=date(2025, 12, 31),
        entity_id=entity.id,
    )
    service.attach_fact_file(
        db_session, run_id=run.id, filename="f.xlsx", data=demo_fact_xlsx
    )
    service.execute_run(db_session, run.id)

    detail = client.get(f"/api/workflows/runs/{run.id}").json()
    files = {f["role"]: f for f in detail["files"]}
    report = files["validation_report"]
    package = files["package_output"]
    assert report["available"] is True
    assert package["available"] is True

    # Fresh run: both downloads succeed.
    assert (
        client.get(f"/api/workflows/run-files/{report['id']}/download").status_code
        == 200
    )
    assert (
        client.get(f"/api/workflows/run-files/{package['id']}/download").status_code
        == 200
    )

    # Delete the report bytes: detail marks it unavailable; download 410s cleanly.
    rf = service.get_run_file(db_session, report["id"])
    (get_settings().data_dir / rf.storage_key).unlink()

    detail2 = client.get(f"/api/workflows/runs/{run.id}").json()
    report2 = next(
        f for f in detail2["files"] if f["role"] == "validation_report"
    )
    assert report2["available"] is False

    gone = client.get(f"/api/workflows/run-files/{report['id']}/download")
    assert gone.status_code == 410
    assert gone.json()["error"]["code"] == "artifact_unavailable"

    # A truly-unknown id is still a plain 404.
    unknown = client.get("/api/workflows/run-files/999999/download")
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "not_found"
