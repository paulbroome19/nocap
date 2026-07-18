"""Workflow endpoints — the demo surface, driven end to end."""

from __future__ import annotations

import io
import zipfile

from fastapi.testclient import TestClient

from app.taxonomy.models import TaxonomySnapshot
from app.workflows.models import Entity, WorkflowConfig


def _create_run(
    client: TestClient, snapshot_id: int, workflow_id: int, entity_id: int
) -> dict:
    resp = client.post(
        "/api/workflows/runs",
        json={
            "workflow_id": workflow_id,
            "snapshot_id": snapshot_id,
            "reference_date": "2025-12-31",
            "entity_id": entity_id,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_list_configs(client: TestClient, lcr_workflow: WorkflowConfig) -> None:
    resp = client.get("/api/workflows/configs")
    assert resp.status_code == 200
    assert "COREP_LCR_DA" in [c["module_code"] for c in resp.json()]


def test_list_entities(client: TestClient, entity: Entity) -> None:
    resp = client.get("/api/workflows/entities")
    assert resp.status_code == 200
    body = resp.json()
    assert any(e["lei"] == entity.lei and e["country"] == "GB" for e in body)


def test_full_flow_one_file_and_download(
    client: TestClient,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
    demo_fact_xlsx: bytes,
) -> None:
    """New default flow: entity + date + one fact file + Run (derived params)."""
    run = _create_run(client, ready_snapshot.id, lcr_workflow.id, entity.id)
    assert run["status"] == "created" and run["entity_lei"] == entity.lei
    run_id = run["id"]

    r = client.post(
        f"/api/workflows/runs/{run_id}/fact-file",
        files={"file": ("facts.xlsx", demo_fact_xlsx, "application/octet-stream")},
    )
    assert r.status_code == 201 and r.json()["fact_count"] == 2

    r = client.post(f"/api/workflows/runs/{run_id}/execute")
    assert r.status_code == 200
    assert r.json()["status"] == "generated", r.text

    detail = client.get(f"/api/workflows/runs/{run_id}").json()
    assert detail["run"]["status"] == "generated"
    assert isinstance(detail["findings"], list)
    outputs = [f for f in detail["files"] if f["role"] == "package_output"]
    assert len(outputs) == 1

    dl = client.get(f"/api/workflows/run-files/{outputs[0]['id']}/download")
    assert dl.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(dl.content))
    assert any(n.endswith("/reports/report.json") for n in zf.namelist())


def test_run_history(
    client: TestClient,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
) -> None:
    run = _create_run(client, ready_snapshot.id, lcr_workflow.id, entity.id)
    hist = client.get(f"/api/workflows/configs/{lcr_workflow.id}/runs")
    assert hist.status_code == 200
    assert any(r["id"] == run["id"] for r in hist.json())


def test_create_run_unknown_workflow_404(
    client: TestClient, ready_snapshot: TaxonomySnapshot, entity: Entity
) -> None:
    resp = client.post(
        "/api/workflows/runs",
        json={
            "workflow_id": 999999,
            "snapshot_id": ready_snapshot.id,
            "reference_date": "2025-12-31",
            "entity_id": entity.id,
        },
    )
    assert resp.status_code == 404
