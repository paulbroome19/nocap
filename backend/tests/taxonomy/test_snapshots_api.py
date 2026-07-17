"""Registry + upload endpoint tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.taxonomy import service


@pytest.fixture(autouse=True)
def _no_background_ingest(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise the background ingest task (it opens its own DB session)."""
    monkeypatch.setattr(service, "ingest_snapshot_task", lambda snapshot_id: None)


def _upload(client: TestClient, data: bytes = b"fake-accdb", label: str = "4.2"):
    return client.post(
        "/api/taxonomy/snapshots",
        data={"version_label": label},
        files={"file": ("DPM.accdb", data, "application/octet-stream")},
    )


def test_upload_registers_snapshot(client: TestClient) -> None:
    resp = _upload(client)
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "ingesting"
    assert body["version_label"] == "4.2"
    assert body["original_filename"] == "DPM.accdb"
    assert len(body["checksum"]) == 64


def test_list_and_detail(client: TestClient) -> None:
    snapshot_id = _upload(client).json()["id"]

    listed = client.get("/api/taxonomy/snapshots")
    assert listed.status_code == 200
    assert any(s["id"] == snapshot_id for s in listed.json())

    detail = client.get(f"/api/taxonomy/snapshots/{snapshot_id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == snapshot_id


def test_detail_missing_returns_404(client: TestClient) -> None:
    resp = client.get("/api/taxonomy/snapshots/999999")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_duplicate_upload_conflicts(client: TestClient) -> None:
    _upload(client, b"identical")
    dup = _upload(client, b"identical")
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "conflict"
