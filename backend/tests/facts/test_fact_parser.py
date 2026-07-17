"""Fact XLSX parser — the nasty cases."""

from __future__ import annotations

from collections.abc import Callable

from app.facts.parsers import parse_fact_xlsx
from tests.facts._xlsx import fact_xlsx

Normalize = Callable[[str], str]


def test_happy_path_mixed_forms_and_leading_zeros(normalize: Normalize) -> None:
    data = fact_xlsx(
        [
            ("C_67_00", "0010", "0010", 100000),  # upstream underscore
            ("C 67.00.a", "0020", "0060", 250000),  # EBA display (space)
            ("C_72.00.a", "0030", "0010", "1.25"),  # DB form, string value
        ]
    )
    result = parse_fact_xlsx(data, normalize=normalize)
    assert result.errors == []
    codes = [(f.template_code, f.row_code, f.column_code) for f in result.facts]
    assert codes == [
        ("C_67.00", "0010", "0010"),
        ("C_67.00.a", "0020", "0060"),
        ("C_72.00.a", "0030", "0010"),
    ]
    assert [f.value for f in result.facts] == ["100000", "250000", "1.25"]


def test_numeric_cells_repadded_to_four_digits(normalize: Normalize) -> None:
    """Excel turns '0010' into the number 10; codes must be re-padded."""
    data = fact_xlsx([("C_67_00", 10, 60, 100000)])
    result = parse_fact_xlsx(data, normalize=normalize)
    assert result.errors == []
    f = result.facts[0]
    assert f.row_code == "0010" and f.column_code == "0060"


def test_whitespace_trimmed(normalize: Normalize) -> None:
    data = fact_xlsx([("  C_67_00  ", " 0010 ", " 0010 ", "  100000  ")])
    result = parse_fact_xlsx(data, normalize=normalize)
    assert result.errors == []
    f = result.facts[0]
    assert f.template_code == "C_67.00"
    assert f.row_code == "0010" and f.value == "100000"


def test_blank_rows_skipped(normalize: Normalize) -> None:
    data = fact_xlsx(
        [
            ("C_67_00", "0010", "0010", 100000),
            (None, None, None, None),
            ("", "", "", ""),
            ("C_67_00", "0020", "0010", 200000),
        ]
    )
    result = parse_fact_xlsx(data, normalize=normalize)
    assert result.errors == []
    assert len(result.facts) == 2


def test_float_integer_value_rendered_without_dot(normalize: Normalize) -> None:
    data = fact_xlsx([("C_67_00", "0010", "0010", 100000.0)])
    result = parse_fact_xlsx(data, normalize=normalize)
    assert result.facts[0].value == "100000"


def test_missing_columns_rejected(normalize: Normalize) -> None:
    data = fact_xlsx(
        [("C_67_00", "0010", 100000)], header=("report", "row", "value")
    )
    result = parse_fact_xlsx(data, normalize=normalize)
    assert result.facts == []
    assert len(result.errors) == 1
    assert "missing columns" in result.errors[0].message


def test_empty_value_cell_reports_row(normalize: Normalize) -> None:
    data = fact_xlsx(
        [
            ("C_67_00", "0010", "0010", 100000),
            ("C_67_00", "0020", "0010", None),  # empty value
        ]
    )
    result = parse_fact_xlsx(data, normalize=normalize)
    assert len(result.facts) == 1
    assert len(result.errors) == 1
    err = result.errors[0]
    assert err.sheet == "facts"
    assert err.row == 3  # header row 1, first data row 2, this one 3
    assert "value" in err.message


def test_bad_template_code_reports_row(normalize: Normalize) -> None:
    data = fact_xlsx([("not-a-code", "0010", "0010", 100000)])
    result = parse_fact_xlsx(data, normalize=normalize)
    assert result.facts == []
    assert result.errors[0].column == "report"
    assert "unrecognised template code" in result.errors[0].message


def test_unreadable_file_is_reported(normalize: Normalize) -> None:
    result = parse_fact_xlsx(b"not an xlsx", normalize=normalize)
    assert result.facts == []
    assert "unreadable" in result.errors[0].message
