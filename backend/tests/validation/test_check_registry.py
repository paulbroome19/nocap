"""The structural check registry — completeness + well-formedness.

Every structural check the validation stage can emit must have a registry entry
(source reference + plain-English description). No check renders without one.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.validation.register import CHECK_BY_CODE, STRUCTURAL_CHECKS

# All-caps, underscore-bearing string literals in the emitting source = the
# finding codes the validation stage raises. (Formula rule ids are lowercase
# "v…_m" and are excluded by this shape; they self-explain via the workbook.)
_CODE_LITERAL = re.compile(r'"([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)"')
_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "app" / "validation"
# Non-code all-caps literals that legitimately appear in the source.
_NON_CODES = {"XBRL"}


def _emitted_codes() -> set[str]:
    codes: set[str] = set()
    for src in (_VALIDATION_DIR / "service.py", _VALIDATION_DIR / "arelle_adapter.py"):
        for m in _CODE_LITERAL.finditer(src.read_text()):
            codes.add(m.group(1))
    return codes - _NON_CODES


def test_every_emitted_structural_code_is_registered() -> None:
    emitted = _emitted_codes()
    # Sanity: the scan actually found the well-known codes.
    assert {"UNRESOLVED_FACT", "DATATYPE_MISMATCH", "NOT_CRLF"} <= emitted
    missing = emitted - set(CHECK_BY_CODE)
    assert not missing, f"emitted checks with no registry entry: {sorted(missing)}"


def test_validator_error_and_meta_codes_registered() -> None:
    # Emitted outside the validation package but still render in the register.
    assert "VALIDATOR_ERROR" in CHECK_BY_CODE
    assert "FORMULA_VALIDATION_UNAVAILABLE" in CHECK_BY_CODE


def test_every_registry_entry_is_well_formed() -> None:
    for c in STRUCTURAL_CHECKS:
        assert c.code and c.ref and c.title and c.description and c.scope
        # The description is a real sentence, not a restated title.
        assert len(c.description) > len(c.title)
        assert c.description[0].isupper() and c.description.rstrip().endswith(".")


def test_registry_codes_are_unique() -> None:
    codes = [c.code for c in STRUCTURAL_CHECKS]
    assert len(codes) == len(set(codes))
