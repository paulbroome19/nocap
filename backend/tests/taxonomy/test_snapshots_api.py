"""Registry + release-creation endpoint tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.taxonomy import service
from app.taxonomy.seed import eba
from tests.fixtures import release_files as rf


@pytest.fixture(autouse=True)
def _no_background_finalize(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise the background finalize task (it opens its own DB session)."""
    monkeypatch.setattr(service, "finalize_release_task", lambda snapshot_id: None)


def _create(client: TestClient, db: Session, dpm: bytes | None = None):
    return client.post(
        "/api/taxonomy/releases",
        data={"version_label": "4.2", "regulator_id": eba(db).id},
        files={
            "dpm_file": ("DPM.accdb", dpm or rf.dpm_bytes()),
            "taxonomy_file": ("taxo.zip", rf.taxonomy_zip_bytes()),
            "rules_file": ("rules.xlsx", rf.rules_bytes()),
        },
    )


def test_create_release_registers_ingesting(
    client: TestClient, db_session: Session
) -> None:
    resp = _create(client, db_session)
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "ingesting"
    assert body["version_label"] == "4.2"
    assert body["original_filename"] == "DPM.accdb"
    assert len(body["checksum"]) == 64


def test_list_and_detail(client: TestClient, db_session: Session) -> None:
    snapshot_id = _create(client, db_session).json()["id"]

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


def test_duplicate_dpm_conflicts(client: TestClient, db_session: Session) -> None:
    _create(client, db_session, dpm=rf.dpm_bytes())
    dup = _create(client, db_session, dpm=rf.dpm_bytes())
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "conflict"
