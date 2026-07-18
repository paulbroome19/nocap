"""The declaration vocabulary + the legacy-value remap used by the migration."""

from __future__ import annotations

from app.workflows.declarations import (
    DECLARATION_NOT_REQUIRED,
    DECLARATION_OPTIONAL,
    DECLARATION_REQUIRED,
    remap_legacy_declarations,
)


def test_remap_maps_legacy_to_current() -> None:
    remapped = remap_legacy_declarations(
        {
            "C_67.00": "auto",
            "C_72.00": "true",
            "C_73.00": "false",
        }
    )
    assert remapped == {
        "C_67.00": DECLARATION_OPTIONAL,
        "C_72.00": DECLARATION_REQUIRED,
        "C_73.00": DECLARATION_NOT_REQUIRED,
    }


def test_remap_is_idempotent_on_current_values() -> None:
    current = {"C_72.00": "required", "C_73.00": "not_required"}
    assert remap_legacy_declarations(current) == current


def test_remap_handles_empty_and_none() -> None:
    assert remap_legacy_declarations({}) == {}
    assert remap_legacy_declarations(None) == {}
