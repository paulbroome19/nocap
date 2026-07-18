"""Release capabilities — derived, never stored.

A release is a kit of functional artifacts; what it *can do* follows from which
artifacts are present and verified. Capabilities are computed on read from the
slot states — nothing derivable is persisted. The one exception is that a run
records the capability set active when it executed (for reproducibility), via
``CapabilitySet.to_dict``.

    resolve          — the DPM database is ready (template/row/col → datapoint).
    generate         — the DPM database is ready (build the xBRL-CSV package);
                       flagged ``verified_entry_points`` when the taxonomy
                       package is also ready (entry points checked against it).
    formula_validate — the taxonomy package is ready (Arelle can run).
    rule_register    — the validation-rules workbook is ready (findings carry the
                       rule statement; activation driven by the reporting date).

Per the dependency rules this imports only ``app.core`` and its own stage.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.taxonomy.artifacts import SlotView
from app.taxonomy.models import ArtifactStatus, ReleaseSlot

# Stable order + labels for the capability panel.
CAPABILITY_LABELS: tuple[tuple[str, str], ...] = (
    ("resolve", "Resolve"),
    ("generate", "Generate"),
    ("formula_validate", "Formula validate"),
    ("rule_register", "Rule register"),
)


@dataclass(frozen=True)
class CapabilitySet:
    resolve: bool
    generate: bool
    verified_entry_points: bool
    formula_validate: bool
    rule_register: bool

    def to_dict(self) -> dict:
        return {
            "resolve": self.resolve,
            "generate": self.generate,
            "verified_entry_points": self.verified_entry_points,
            "formula_validate": self.formula_validate,
            "rule_register": self.rule_register,
        }


def _ready(views: Sequence[SlotView], slot: ReleaseSlot) -> bool:
    view = next((v for v in views if v.spec.slot is slot), None)
    return view is not None and view.status is ArtifactStatus.ready


def derive_capabilities(slot_views: Sequence[SlotView]) -> CapabilitySet:
    """Capabilities implied by a release's current slot states."""
    dpm = _ready(slot_views, ReleaseSlot.dpm_database)
    taxonomy = _ready(slot_views, ReleaseSlot.taxonomy_package)
    validation_rules = _ready(slot_views, ReleaseSlot.validation_rules)
    return CapabilitySet(
        resolve=dpm,
        generate=dpm,
        verified_entry_points=dpm and taxonomy,
        formula_validate=taxonomy,
        rule_register=validation_rules,
    )
