"""Indicators & parameters parser."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from app.facts.parsers import XlsxIndicatorsParamsParser
from tests.facts._xlsx import indicators_params_xlsx

Normalize = Callable[[str], str]

_GOOD_PARAMS = [
    ("entity_lei", "5299001234567890ABCD"),
    ("reference_date", "2025-12-31"),
    ("base_currency", "EUR"),
    ("decimals", -3),
]
_GOOD_INDICATORS = [("C_73.00.a", True), ("C 74.00.a", True), ("C_76_00_a", False)]


def _parse(data: bytes, normalize: Normalize):
    return XlsxIndicatorsParamsParser().parse(data, normalize=normalize)


def test_happy_path(normalize: Normalize) -> None:
    data = indicators_params_xlsx(_GOOD_PARAMS, _GOOD_INDICATORS)
    result = _parse(data, normalize)
    assert result.errors == []
    p = result.params
    assert p is not None
    assert p.entity_lei == "5299001234567890ABCD"
    assert p.reference_date == date(2025, 12, 31)
    assert p.base_currency == "EUR"
    assert p.decimals == -3
    # indicator codes normalised to canonical DB form; reported flag honoured
    assert [(i.template_code, i.reported) for i in p.filing_indicators] == [
        ("C_73.00.a", True),
        ("C_74.00.a", True),
        ("C_76.00.a", False),
    ]


def test_malformed_lei_rejected(normalize: Normalize) -> None:
    params = [("entity_lei", "TOO-SHORT")] + _GOOD_PARAMS[1:]
    result = _parse(indicators_params_xlsx(params, _GOOD_INDICATORS), normalize)
    assert result.params is None
    assert any(e.column == "entity_lei" for e in result.errors)


def test_unparseable_date_rejected(normalize: Normalize) -> None:
    params = [_GOOD_PARAMS[0], ("reference_date", "31/12/2025")] + _GOOD_PARAMS[2:]
    result = _parse(indicators_params_xlsx(params, _GOOD_INDICATORS), normalize)
    assert result.params is None
    assert any(e.column == "reference_date" for e in result.errors)


def test_missing_param_rejected(normalize: Normalize) -> None:
    params = _GOOD_PARAMS[:2] + _GOOD_PARAMS[3:]  # drop base_currency
    result = _parse(indicators_params_xlsx(params, _GOOD_INDICATORS), normalize)
    assert result.params is None
    assert any("base_currency" in e.message for e in result.errors)


def test_missing_sheet_rejected(normalize: Normalize) -> None:
    data = indicators_params_xlsx(_GOOD_PARAMS, [], indicators_sheet=None)
    result = _parse(data, normalize)
    assert result.params is None
    assert any("filing_indicators" in e.message for e in result.errors)


def test_bad_indicator_code_rejected(normalize: Normalize) -> None:
    data = indicators_params_xlsx(_GOOD_PARAMS, [("junk-code", True)])
    result = _parse(data, normalize)
    assert result.params is None
    assert any("unrecognised template code" in e.message for e in result.errors)
