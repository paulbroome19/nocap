"""Regulators: seeding, the API, business naming, and release scoping."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.taxonomy import service
from app.taxonomy.models import Regulator
from app.taxonomy.seed import eba, seed_regulators


def test_seed_is_idempotent(db_session: Session) -> None:
    assert seed_regulators(db_session) == 1  # EBA
    assert seed_regulators(db_session) == 0
    assert eba(db_session).code == "EBA"


def test_regulators_endpoint_lists_eba(client: TestClient, db_session: Session) -> None:
    eba(db_session)
    body = client.get("/api/taxonomy/regulators").json()
    assert any(r["code"] == "EBA" and r["name"] == "European Banking Authority"
               for r in body)


def test_release_carries_business_name(client: TestClient, db_session: Session) -> None:
    snap = service.register_snapshot(
        db_session, file_bytes=b"x", filename="DPM.accdb", version_label="4.2",
    )
    body = client.get(f"/api/taxonomy/snapshots/{snap.id}").json()
    assert body["display_name"] == "EBA Taxonomy 4.2"
    assert body["regulator_code"] == "EBA"
    # The raw filename is still present as evidence, not the primary label.
    assert body["original_filename"] == "DPM.accdb"


def test_releases_are_scoped_to_their_regulator(
    client: TestClient, db_session: Session
) -> None:
    eba_id = eba(db_session).id
    # A second publisher with its own release.
    other = Regulator(code="PRA", name="Prudential Regulation Authority")
    db_session.add(other)
    db_session.commit()
    service.register_snapshot(
        db_session, file_bytes=b"eba", filename="e.accdb", version_label="4.2",
        regulator_id=eba_id,
    )
    service.register_snapshot(
        db_session, file_bytes=b"pra", filename="p.accdb", version_label="1.0",
        regulator_id=other.id,
    )

    eba_releases = client.get(f"/api/taxonomy/regulators/{eba_id}/releases").json()
    assert {r["version_label"] for r in eba_releases} == {"4.2"}
    assert all(r["regulator_code"] == "EBA" for r in eba_releases)

    pra_releases = client.get(f"/api/taxonomy/regulators/{other.id}/releases").json()
    assert {r["version_label"] for r in pra_releases} == {"1.0"}
