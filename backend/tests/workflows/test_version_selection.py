"""Taxonomy version selection: dedup across releases + ingestion summary.

The worked example from the spec: load EBA 4.2, 4.2.1, 4.2.2. COREP_LCR_DA is
3.3.0 in all three (one option); FINREP9 is 3.4.0 / 3.4.1 / 3.4.2 (three).
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.taxonomy import service as taxonomy
from app.taxonomy.models import SnapshotStatus, TaxonomySnapshot
from app.taxonomy.seed import eba
from app.workflows import version_selection as vs
from app.workflows.models import WorkflowConfig
from tests.fixtures.dpm_modules import build_dpm

# (module_code, framework_code, version, name) per release.
_LCR = ("COREP_LCR_DA", "COREP", "3.3.0", "LCR Delegated Act - COREP")


def _release(db: Session, code: str, modules) -> TaxonomySnapshot:
    """Register a ready snapshot whose DPM provides ``modules``, and record them."""
    settings = get_settings()
    snap = TaxonomySnapshot(
        regulator_id=eba(db).id,
        version_label=code,
        original_filename=f"DPM_{code}.accdb",
        checksum=f"chk-{code}",
        status=SnapshotStatus.ready,
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    taxonomy.snapshot_dir(settings, snap.id).mkdir(parents=True, exist_ok=True)
    build_dpm(taxonomy._sqlite_path(settings, snap.id), code, modules)
    taxonomy.record_release_modules(db, snap, settings=settings)
    return snap


@pytest.fixture
def three_releases(db_session: Session):
    """EBA 4.2, 4.2.1, 4.2.2 — LCR unchanged, FINREP9 bumped each release."""
    def fin(v):
        return ("FINREP9", "FINREP", v, "Finrep")

    s42 = _release(db_session, "4.2", [_LCR, fin("3.4.0")])
    s421 = _release(db_session, "4.2.1", [_LCR, fin("3.4.1")])
    s422 = _release(db_session, "4.2.2", [_LCR, fin("3.4.2")])
    return s42, s421, s422


def _wf(db: Session, name: str, module_code: str) -> WorkflowConfig:
    wf = WorkflowConfig(
        name=name, framework_code=module_code.split("_")[0],
        module_code=module_code, is_active=True,
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    return wf


def test_unchanged_module_collapses_to_one_option(
    db_session: Session, three_releases
) -> None:
    """COREP_LCR_DA is 3.3.0@4.2 in all three releases → one option."""
    wf = _wf(db_session, "COREP LCR", "COREP_LCR_DA")
    result = vs.list_module_versions(db_session, wf.id)
    assert len(result.options) == 1
    opt = result.options[0]
    assert (opt.module_version, opt.framework_version) == ("3.3.0", "4.2")
    # All three releases provide it — detail, newest first.
    assert opt.provided_by == ["EBA Taxonomy 4.2.2", "EBA Taxonomy 4.2.1",
                               "EBA Taxonomy 4.2"]
    # A run binds to the newest release providing it.
    s42, s421, s422 = three_releases
    assert opt.snapshot_id == s422.id


def test_changed_module_presents_distinct_options(
    db_session: Session, three_releases
) -> None:
    """FINREP9 differs per release → three distinct options, newest first."""
    wf = _wf(db_session, "FINREP 9", "FINREP9")
    result = vs.list_module_versions(db_session, wf.id)
    versions = [o.module_version for o in result.options]
    assert versions == ["3.4.2", "3.4.1", "3.4.0"]
    # Each is provided by exactly its own release, which the run binds to.
    s42, s421, s422 = three_releases
    by_ver = {o.module_version: o for o in result.options}
    assert by_ver["3.4.0"].snapshot_id == s42.id
    assert by_ver["3.4.1"].snapshot_id == s421.id
    assert by_ver["3.4.2"].snapshot_id == s422.id
    assert by_ver["3.4.0"].provided_by == ["EBA Taxonomy 4.2"]


def test_selector_lists_only_releases_containing_the_module(
    db_session: Session
) -> None:
    """A release that doesn't contain the module contributes no option."""
    _release(db_session, "4.2", [_LCR])  # no FINREP9
    wf = _wf(db_session, "FINREP 9", "FINREP9")
    assert vs.list_module_versions(db_session, wf.id).options == []


def test_ingestion_summary_new_vs_existing(
    db_session: Session, three_releases
) -> None:
    """Summary for EBA 4.2.1: FINREP9 3.4.1 is new; COREP_LCR_DA 3.3.0 already
    from EBA 4.2."""
    _wf(db_session, "COREP LCR", "COREP_LCR_DA")
    _wf(db_session, "FINREP 9", "FINREP9")
    s42, s421, s422 = three_releases

    summary = vs.release_provisions_summary(db_session, s421.id)
    by_mod = {p.module_code: p for p in summary.provisions}

    assert by_mod["FINREP9"].module_version == "3.4.1"
    assert by_mod["FINREP9"].is_new is True
    assert by_mod["FINREP9"].already_from is None

    assert by_mod["COREP_LCR_DA"].module_version == "3.3.0"
    assert by_mod["COREP_LCR_DA"].is_new is False
    assert by_mod["COREP_LCR_DA"].already_from == "EBA Taxonomy 4.2"


def test_ingestion_summary_reports_module_absent(db_session: Session) -> None:
    """A suite whose module the release doesn't contain reads as absent."""
    s = _release(db_session, "4.2", [_LCR])
    _wf(db_session, "FINREP 9", "FINREP9")
    summary = vs.release_provisions_summary(db_session, s.id)
    finrep = next(p for p in summary.provisions if p.module_code == "FINREP9")
    assert finrep.module_version is None and finrep.is_new is False


# --- endpoints (API layer + serialization) ---------------------------------


def test_module_versions_endpoint(client, db_session, three_releases) -> None:
    wf = _wf(db_session, "FINREP 9", "FINREP9")
    resp = client.get(f"/api/workflows/configs/{wf.id}/module-versions")
    assert resp.status_code == 200
    body = resp.json()
    assert [o["module_version"] for o in body["options"]] == [
        "3.4.2", "3.4.1", "3.4.0",
    ]
    # Nothing is preselected — the client renders no default choice.
    assert body["module_code"] == "FINREP9"


def test_module_versions_endpoint_empty_when_absent(client, db_session) -> None:
    _release(db_session, "4.2", [_LCR])  # no FINREP9
    wf = _wf(db_session, "FINREP 9", "FINREP9")
    resp = client.get(f"/api/workflows/configs/{wf.id}/module-versions")
    assert resp.status_code == 200 and resp.json()["options"] == []


def test_create_run_freezes_module_and_framework_version(
    db_session, ready_snapshot, lcr_workflow, entity
) -> None:
    """A run records the module version + framework version it bound to, so its
    history is reproducible even after later releases change what's provided."""
    from datetime import date

    from app.workflows import service as wf_service

    run = wf_service.create_run(
        db_session,
        workflow_id=lcr_workflow.id,
        snapshot_id=ready_snapshot.id,
        reference_date=date(2026, 3, 31),
        entity_id=entity.id,
    )
    # mini DPM: COREP_LCR_DA VersionNumber 3.3.0 at release code 4.2.
    assert run.module_version == "3.3.0"
    assert run.framework_version == "4.2"


def test_provisions_endpoint(client, db_session, three_releases) -> None:
    _wf(db_session, "COREP LCR", "COREP_LCR_DA")
    _wf(db_session, "FINREP 9", "FINREP9")
    s42, s421, s422 = three_releases
    resp = client.get(f"/api/workflows/releases/{s421.id}/provisions")
    assert resp.status_code == 200
    by_mod = {p["module_code"]: p for p in resp.json()["provisions"]}
    assert by_mod["FINREP9"]["is_new"] is True
    assert by_mod["COREP_LCR_DA"]["already_from"] == "EBA Taxonomy 4.2"
