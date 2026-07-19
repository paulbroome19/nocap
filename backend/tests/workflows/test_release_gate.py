"""Empirical coherence gate — the taxonomy package must load in Arelle for the
DPM's current-release entry point (workflows.release_gate).

The Arelle load itself is stubbed here (it is exercised end-to-end against a real
release elsewhere); these tests pin the orchestration: it builds the DPM entry
point, gates on the load result, and stays silent when Arelle is disabled.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ValidationError
from app.taxonomy.models import TaxonomySnapshot
from app.workflows import release_gate
from app.workflows.models import WorkflowConfig

_UNRESOLVABLE = [
    {"level": "error", "code": "xbrlce:unresolvableBaseMetadataFile"}
]


def _arelle_on() -> object:
    return get_settings().model_copy(update={"arelle_enabled": True})


@pytest.fixture
def _wire(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> pytest.MonkeyPatch:
    # The gate opens its own session for workflow configs and reads the taxonomy
    # packages off disk — point both at this test's data.
    monkeypatch.setattr(
        release_gate, "SessionLocal", lambda: contextlib.nullcontext(db_session)
    )
    monkeypatch.setattr(
        release_gate.taxonomy,
        "snapshot_taxonomy_packages",
        lambda _s, _sid: [Path("taxonomy.zip")],  # stubbed loader ignores it
    )
    return monkeypatch


def test_gate_raises_when_entry_point_unresolvable(
    _wire: pytest.MonkeyPatch,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
) -> None:
    _wire.setattr(
        release_gate.arelle_adapter,
        "taxonomy_load_errors",
        lambda *_a, **_k: _UNRESOLVABLE,
    )
    with pytest.raises(ValidationError, match="does not match the DPM"):
        release_gate.verify_release_taxonomy_loads(ready_snapshot.id, _arelle_on())


def test_gate_passes_when_taxonomy_loads(
    _wire: pytest.MonkeyPatch,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
) -> None:
    _wire.setattr(
        release_gate.arelle_adapter,
        "taxonomy_load_errors",
        lambda *_a, **_k: [],  # loaded cleanly
    )
    # No raise.
    release_gate.verify_release_taxonomy_loads(ready_snapshot.id, _arelle_on())


def test_gate_skipped_when_arelle_disabled(
    _wire: pytest.MonkeyPatch,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
) -> None:
    called = {"n": 0}

    def _boom(*_a, **_k):
        called["n"] += 1
        return _UNRESOLVABLE

    _wire.setattr(release_gate.arelle_adapter, "taxonomy_load_errors", _boom)
    # arelle_enabled defaults to False in tests → the gate must not run Arelle.
    release_gate.verify_release_taxonomy_loads(ready_snapshot.id, get_settings())
    assert called["n"] == 0
