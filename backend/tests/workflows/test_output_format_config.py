"""Per-(regulator, workflow) output-format configuration: service + API."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.generation.schemas import OutputFormat
from app.taxonomy.models import TaxonomySnapshot
from app.workflows import service
from app.workflows.models import WorkflowConfig


def test_default_is_xbrl_csv_without_config(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
) -> None:
    rid = ready_snapshot.regulator_id
    assert service.get_regulator_format_default(db_session, rid) is (
        OutputFormat.xbrl_csv
    )
    assert (
        service.resolve_output_format(
            db_session, regulator_id=rid, workflow_id=lcr_workflow.id
        )
        is OutputFormat.xbrl_csv
    )


def test_regulator_default_applies_when_no_override(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
) -> None:
    rid = ready_snapshot.regulator_id
    service.set_regulator_format_default(
        db_session, regulator_id=rid, output_format=OutputFormat.xbrl_xml
    )
    assert (
        service.resolve_output_format(
            db_session, regulator_id=rid, workflow_id=lcr_workflow.id
        )
        is OutputFormat.xbrl_xml
    )


def test_workflow_override_wins_over_default(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
) -> None:
    rid = ready_snapshot.regulator_id
    # Regulator default XML, but this suite is pinned to CSV.
    service.set_regulator_format_default(
        db_session, regulator_id=rid, output_format=OutputFormat.xbrl_xml
    )
    service.set_workflow_format_override(
        db_session,
        regulator_id=rid,
        workflow_id=lcr_workflow.id,
        output_format=OutputFormat.xbrl_csv,
    )
    assert (
        service.resolve_output_format(
            db_session, regulator_id=rid, workflow_id=lcr_workflow.id
        )
        is OutputFormat.xbrl_csv
    )
    # Clearing the override falls back to the regulator default.
    service.clear_workflow_format_override(
        db_session, regulator_id=rid, workflow_id=lcr_workflow.id
    )
    assert (
        service.resolve_output_format(
            db_session, regulator_id=rid, workflow_id=lcr_workflow.id
        )
        is OutputFormat.xbrl_xml
    )


def test_upsert_updates_in_place(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
) -> None:
    rid = ready_snapshot.regulator_id
    service.set_workflow_format_override(
        db_session,
        regulator_id=rid,
        workflow_id=lcr_workflow.id,
        output_format=OutputFormat.xbrl_xml,
    )
    service.set_workflow_format_override(
        db_session,
        regulator_id=rid,
        workflow_id=lcr_workflow.id,
        output_format=OutputFormat.xbrl_csv,
    )
    assert (
        service.get_workflow_format_override(db_session, rid, lcr_workflow.id)
        is OutputFormat.xbrl_csv
    )


# --- API ------------------------------------------------------------------


def test_regulator_format_endpoints(
    client: TestClient,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
) -> None:
    rid = ready_snapshot.regulator_id
    r = client.get(f"/api/workflows/regulators/{rid}/format")
    assert r.status_code == 200
    assert r.json() == {"regulator_id": rid, "output_format": "xbrl_csv"}

    r = client.put(
        f"/api/workflows/regulators/{rid}/format",
        json={"output_format": "xbrl_xml"},
    )
    assert r.status_code == 200
    assert r.json()["output_format"] == "xbrl_xml"

    # Unknown regulator → 404.
    assert client.get("/api/workflows/regulators/9999/format").status_code == 404


def test_workflow_format_endpoints(
    client: TestClient,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
) -> None:
    rid = ready_snapshot.regulator_id
    wid = lcr_workflow.id

    # No override yet: effective == regulator default, overridden False.
    r = client.get(f"/api/workflows/regulators/{rid}/configs/{wid}/format")
    assert r.status_code == 200
    body = r.json()
    assert body["output_format"] == "xbrl_csv"
    assert body["overridden"] is False
    assert body["regulator_default"] == "xbrl_csv"

    # Set an override.
    r = client.put(
        f"/api/workflows/regulators/{rid}/configs/{wid}/format",
        json={"output_format": "xbrl_xml"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["output_format"] == "xbrl_xml"
    assert body["overridden"] is True
    assert body["regulator_default"] == "xbrl_csv"

    # Clear it.
    r = client.delete(f"/api/workflows/regulators/{rid}/configs/{wid}/format")
    assert r.status_code == 200
    assert r.json()["overridden"] is False

    # Unknown workflow → 404.
    assert (
        client.get(
            f"/api/workflows/regulators/{rid}/configs/9999/format"
        ).status_code
        == 404
    )
