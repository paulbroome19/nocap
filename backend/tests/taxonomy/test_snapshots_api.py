"""Registry + release-creation endpoint tests (synchronous, all-or-nothing)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.taxonomy.seed import eba
from tests.fixtures import dpm_mini
from tests.fixtures import release_files as rf


@pytest.fixture
def dpm_sqlite(tmp_path: Path) -> bytes:
    """A pre-converted mini DPM, so the endpoint needs no mdbtools converter."""
    return dpm_mini.build(tmp_path / "dpm.sqlite").read_bytes()


def _create(client: TestClient, db: Session, dpm: bytes):
    return client.post(
        "/api/taxonomy/releases",
        data={"version_label": "4.2", "regulator_id": eba(db).id},
        files={
            "dpm_file": ("dpm.sqlite", dpm),
            "taxonomy_file": ("taxo.zip", rf.taxonomy_zip_bytes()),
            "rules_file": ("rules.xlsx", rf.rules_bytes()),
        },
    )


def test_create_release_is_ready(
    client: TestClient, db_session: Session, dpm_sqlite: bytes
) -> None:
    resp = _create(client, db_session, dpm_sqlite)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "ready"  # never 'ingesting' — creation is synchronous
    assert body["version_label"] == "4.2"
    assert body["original_filename"] == "dpm.sqlite"
    assert len(body["checksum"]) == 64


def test_list_and_detail(
    client: TestClient, db_session: Session, dpm_sqlite: bytes
) -> None:
    snapshot_id = _create(client, db_session, dpm_sqlite).json()["id"]

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


def test_duplicate_dpm_conflicts(
    client: TestClient, db_session: Session, dpm_sqlite: bytes
) -> None:
    _create(client, db_session, dpm_sqlite)
    dup = _create(client, db_session, dpm_sqlite)
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "conflict"
