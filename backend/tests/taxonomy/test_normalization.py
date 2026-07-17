"""Template-code normalisation — all three input forms, leading zeros, errors."""

from __future__ import annotations

import pytest

from app.taxonomy.service import normalize_template_code as norm


@pytest.mark.parametrize(
    "raw",
    [
        "C_67_00",  # upstream (all underscores)
        "C_67.00",  # DB form
        "C 67.00",  # EBA display form
        "c 67.00",  # lowercase letters
        "  C_67_00  ",  # surrounding whitespace
    ],
)
def test_all_input_forms_canonicalise_to_db_form(raw: str) -> None:
    assert norm(raw) == "C_67.00"


def test_eba_output_form() -> None:
    assert norm("C_67_00", form="eba") == "C 67.00"
    assert norm("C_67.00.a", form="eba") == "C 67.00.a"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("C_67.00.a", "C_67.00.a"),  # lowercase variant suffix preserved
        ("C_67_00_w", "C_67.00.w"),  # upstream suffix underscore -> dot
        ("C 67.00.a", "C_67.00.a"),
    ],
)
def test_variant_suffixes(raw: str, expected: str) -> None:
    assert norm(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("C_00.01", "C_00.01"),  # leading zeros in both parts
        ("C_07.00", "C_07.00"),  # leading zero in major
        ("F_01.03", "F_01.03"),
        ("C 00.01", "C_00.01"),
    ],
)
def test_leading_zeros_preserved(raw: str, expected: str) -> None:
    """Leading zeros are significant and must never be dropped."""
    assert norm(raw) == expected


@pytest.mark.parametrize(
    "bad",
    ["", "junk", "6700", "C__", "67.00", "C_67", "C-67-00"],
)
def test_unrecognised_codes_raise(bad: str) -> None:
    with pytest.raises(ValueError):
        norm(bad)


def test_unknown_form_raises() -> None:
    with pytest.raises(ValueError):
        norm("C_67.00", form="xbrl")
