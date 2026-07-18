"""The register join: workbook descriptions on formula rows + deactivated flags."""

from __future__ import annotations

from app.validation.register import build_register

# A formula summary as workflows persists it: one evaluated rule + one that the
# taxonomy traced but the workbook deactivated for the reporting date.
_FORMULA = {
    "status": "executed",
    "loaded": 3,
    "evaluated": 1,
    "satisfied": 0,
    "unsatisfied": 1,
    "rules": [
        {
            "rule_id": "v16053_m",
            "assertion_type": "Value Assertion",
            "satisfied": 0,
            "not_satisfied": 1,
            "result": "FAILED",
            "values": "57621 >= 66241",
            "message": "{D_02.00.a,0060,0100,} >= ... Fails.",
        },
    ],
    "deactivated": ["v6272_m"],  # traced but excluded
    "note": None,
}

_RULE_META = {
    "descriptions": {
        "v16053_m": "{C 02.00, r0060} >= {C 02.00, r0070}",
        "v6272_m": "{C 08.01.b} = sum({C 08.02})",
    },
    "inactive": {"v6272_m": "{C 08.01.b} = sum({C 08.02})"},
}


def test_formula_row_gains_description() -> None:
    rows = build_register([], _FORMULA, rule_meta=_RULE_META)
    executed = next(r for r in rows if r.id == "v16053_m")
    assert executed.rule_text == "{C 02.00, r0060} >= {C 02.00, r0070}"
    assert executed.result == "FAILED"


def test_deactivated_rule_is_flagged_not_dropped() -> None:
    rows = build_register([], _FORMULA, rule_meta=_RULE_META)
    flagged = next(r for r in rows if r.id == "v6272_m")
    assert flagged.result == "DEACTIVATED"
    assert flagged.source == "formula"
    assert "inactive" in flagged.detail
    assert flagged.rule_text == "{C 08.01.b} = sum({C 08.02})"


def test_no_rule_meta_leaves_rows_bare() -> None:
    # Without a workbook, formula rows have no rule_text and nothing is flagged.
    rows = build_register([], _FORMULA)
    executed = next(r for r in rows if r.id == "v16053_m")
    assert executed.rule_text is None
    assert all(r.result != "DEACTIVATED" for r in rows)


def test_hardcoded_fallback_deactivation_not_flagged() -> None:
    # A deactivation with no workbook description (hardcoded fallback) is not
    # surfaced as a workbook-flagged row.
    rows = build_register([], _FORMULA, rule_meta={"descriptions": {}, "inactive": {}})
    assert all(r.result != "DEACTIVATED" for r in rows)
