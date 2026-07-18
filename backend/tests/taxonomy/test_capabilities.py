"""Capability derivation — the matrix over which functional slots are ready."""

from __future__ import annotations

import pytest

from app.taxonomy import capabilities as caps
from app.taxonomy.artifacts import SlotView, slot_spec
from app.taxonomy.models import ArtifactStatus, ReleaseSlot


def _views(ready: set[ReleaseSlot]) -> list[SlotView]:
    """SlotViews for every slot, ``ready`` ones ready and the rest empty."""
    out = []
    for slot in ReleaseSlot:
        status = (
            ArtifactStatus.ready if slot in ready else ArtifactStatus.empty
        )
        out.append(
            SlotView(slot_spec(slot), status, None, None, None, None)
        )
    return out


D = ReleaseSlot.dpm_database
T = ReleaseSlot.taxonomy_package
V = ReleaseSlot.validation_rules


@pytest.mark.parametrize(
    "ready,expected",
    [
        # nothing ready → no capability
        (set(), (False, False, False, False, False)),
        # DPM only → resolve + generate (no verified entry points)
        ({D}, (True, True, False, False, False)),
        # DPM + taxonomy → generate is verified, formula validation on
        ({D, T}, (True, True, True, True, False)),
        # DPM + workbook → rule register on, but generate not verified
        ({D, V}, (True, True, False, False, True)),
        # full kit → everything
        ({D, T, V}, (True, True, True, True, True)),
        # taxonomy without DPM → formula flag on, but cannot resolve/generate
        ({T}, (False, False, False, True, False)),
    ],
)
def test_capability_matrix(ready, expected) -> None:
    c = caps.derive_capabilities(_views(ready))
    got = (
        c.resolve,
        c.generate,
        c.verified_entry_points,
        c.formula_validate,
        c.rule_register,
    )
    assert got == expected


def test_verifying_dpm_is_not_ready() -> None:
    views = [
        SlotView(slot_spec(D), ArtifactStatus.verifying, None, None, None, None)
    ]
    c = caps.derive_capabilities(views)
    assert c.resolve is False and c.generate is False


def test_to_dict_round_trips() -> None:
    c = caps.derive_capabilities(_views({D, T, V}))
    assert c.to_dict() == {
        "resolve": True,
        "generate": True,
        "verified_entry_points": True,
        "formula_validate": True,
        "rule_register": True,
    }
