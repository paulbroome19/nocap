"""Workflow categories, active filtering, and settings persistence."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.workflows import service
from app.workflows.seed import seed_workflow_configs

# Expected active catalogue after seeding.
ACTIVE = {
    "Liquidity": {"COREP_LCR_DA", "COREP_NSFR", "AE", "COREP_ALM"},
    "Capital": {"COREP_OF", "COREP_LR", "COREP_LE", "COREP_FRTB"},
    "Financial": {"FINREP9"},
    "Last Mile Reporting": {"IF_CLASS2", "IRRBB", "P3DH", "REM_HE_CI", "RESOL2"},
}


def test_seed_integrity_categories_and_names(db_session: Session) -> None:
    assert seed_workflow_configs(db_session) == 20
    assert seed_workflow_configs(db_session) == 0  # idempotent upsert

    active = service.list_workflows(db_session)
    assert len(active) == 14
    by_cat: dict[str, set[str]] = {}
    for w in active:
        by_cat.setdefault(w.category, set()).add(w.module_code)
    assert by_cat == ACTIVE

    # Clean display names (no "COREP —" prefix); module code is the subtitle.
    lcr = next(w for w in active if w.module_code == "COREP_LCR_DA")
    assert lcr.name == "LCR"
    of = next(w for w in active if w.module_code == "COREP_OF")
    assert of.name == "Own Funds"

    # Inactive suites exist but are hidden from the active list.
    everything = service.list_workflows(db_session, active_only=False)
    assert len(everything) == 20
    mrel = next(w for w in everything if w.module_code == "MREL_TLAC")
    assert mrel.is_active is False and mrel.category is None


def test_configs_endpoint_filtering(client, db_session: Session) -> None:
    seed_workflow_configs(db_session)
    assert len(client.get("/api/workflows/configs").json()) == 14
    assert (
        len(client.get("/api/workflows/configs?include_inactive=true").json()) == 20
    )
    liq = client.get("/api/workflows/configs?category=Liquidity").json()
    assert {w["module_code"] for w in liq} == ACTIVE["Liquidity"]


def test_categories_endpoint_counts(client, db_session: Session) -> None:
    seed_workflow_configs(db_session)
    body = client.get("/api/workflows/categories").json()
    # Curated display order — Capital leads, not alphabetical.
    assert [c["category"] for c in body] == [
        "Capital", "Liquidity", "Financial", "Last Mile Reporting",
    ]
    cats = {c["category"]: c for c in body}
    assert set(cats) == set(ACTIVE)
    assert cats["Liquidity"]["active_count"] == 4
    assert cats["Capital"]["active_count"] == 4
    assert cats["Financial"]["active_count"] == 1
    assert cats["Last Mile Reporting"]["active_count"] == 5
    assert cats["Liquidity"]["last_run"] is None  # no runs yet


def test_category_suites_endpoint(client, db_session: Session) -> None:
    seed_workflow_configs(db_session)
    suites = client.get(
        "/api/workflows/categories/Liquidity/suites"
    ).json()
    assert {s["module_code"] for s in suites} == ACTIVE["Liquidity"]
    assert all(s["last_run"] is None for s in suites)


def test_settings_update_persists_live(client, db_session: Session) -> None:
    seed_workflow_configs(db_session)
    everything = client.get(
        "/api/workflows/configs?include_inactive=true"
    ).json()
    inactive = next(w for w in everything if not w["is_active"])

    resp = client.patch(
        f"/api/workflows/configs/{inactive['id']}",
        json={"category": "Capital", "is_active": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["category"] == "Capital" and body["is_active"] is True

    # Now surfaces in the active list under Capital.
    active_codes = {
        w["module_code"] for w in client.get("/api/workflows/configs").json()
    }
    assert inactive["module_code"] in active_codes

    # Deactivating hides it again.
    client.patch(
        f"/api/workflows/configs/{inactive['id']}",
        json={"category": None, "is_active": False},
    )
    active_codes = {
        w["module_code"] for w in client.get("/api/workflows/configs").json()
    }
    assert inactive["module_code"] not in active_codes


def test_settings_rejects_unknown_category(client, db_session: Session) -> None:
    seed_workflow_configs(db_session)
    wf = client.get("/api/workflows/configs").json()[0]
    bad = client.patch(
        f"/api/workflows/configs/{wf['id']}",
        json={"category": "Nonsense", "is_active": True},
    )
    assert bad.status_code == 422
