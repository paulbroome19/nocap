"""Workflow endpoints — the demo surface, driven end to end."""

from __future__ import annotations

import zipfile

from fastapi.testclient import TestClient

from app.taxonomy.models import TaxonomySnapshot
from app.workflows.models import WorkflowConfig
from tests.workflows.conftest import ENTITY


def _create_run(client: TestClient, snapshot_id: int, workflow_id: int) -> dict:
    resp = client.post(
        "/api/workflows/runs",
        json={
            "workflow_id": workflow_id,
            "snapshot_id": snapshot_id,
            "reference_date": "2025-12-31",
            "entity_lei": ENTITY,
            "entity_scope": "CON",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_list_configs(client: TestClient, lcr_workflow: WorkflowConfig) -> None:
    resp = client.get("/api/workflows/configs")
    assert resp.status_code == 200
    codes = [c["module_code"] for c in resp.json()]
    assert "COREP_LCR_DA" in codes


def test_full_flow_and_download(
    client: TestClient,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    demo_fact_xlsx: bytes,
    demo_indicators_xlsx: bytes,
) -> None:
    run = _create_run(client, ready_snapshot.id, lcr_workflow.id)
    assert run["status"] == "created"
    run_id = run["id"]

    r = client.post(
        f"/api/workflows/runs/{run_id}/fact-file",
        files={"file": ("facts.xlsx", demo_fact_xlsx, "application/octet-stream")},
    )
    assert r.status_code == 201 and r.json()["fact_count"] == 2

    r = client.post(
        f"/api/workflows/runs/{run_id}/indicators-params-file",
        files={"file": ("ip.xlsx", demo_indicators_xlsx, "application/octet-stream")},
    )
    assert r.status_code == 201

    r = client.post(f"/api/workflows/runs/{run_id}/execute")
    assert r.status_code == 200
    assert r.json()["status"] == "generated", r.text

    detail = client.get(f"/api/workflows/runs/{run_id}").json()
    assert detail["run"]["status"] == "generated"
    outputs = [f for f in detail["files"] if f["role"] == "package_output"]
    assert len(outputs) == 1

    # Download the generated package and confirm it's a valid zip.
    dl = client.get(f"/api/workflows/run-files/{outputs[0]['id']}/download")
    assert dl.status_code == 200
    zf = zipfile.ZipFile(__import__("io").BytesIO(dl.content))
    assert any(n.endswith("/reports/report.json") for n in zf.namelist())


def test_run_history(
    client: TestClient,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
) -> None:
    run = _create_run(client, ready_snapshot.id, lcr_workflow.id)
    hist = client.get(f"/api/workflows/configs/{lcr_workflow.id}/runs")
    assert hist.status_code == 200
    assert any(r["id"] == run["id"] for r in hist.json())


def test_create_run_unknown_workflow_404(
    client: TestClient, ready_snapshot: TaxonomySnapshot
) -> None:
    resp = client.post(
        "/api/workflows/runs",
        json={
            "workflow_id": 999999,
            "snapshot_id": ready_snapshot.id,
            "reference_date": "2025-12-31",
            "entity_lei": ENTITY,
        },
    )
    assert resp.status_code == 404
