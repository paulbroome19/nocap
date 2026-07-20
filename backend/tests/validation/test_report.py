"""The validation rule register + the HTML report that mirrors it."""

from __future__ import annotations

from app.validation.models import Severity, ValidationPhase
from app.validation.register import build_register
from app.validation.report import build_report_html
from app.validation.schemas import Finding


def _f(code, severity=Severity.error, phase=ValidationPhase.pre_generation, **loc):
    return Finding(
        severity=severity, phase=phase, code=code, message=f"{code} message", **loc
    )


def test_register_clean_run_all_passed_with_ids() -> None:
    rows = build_register([], None)
    assert all(r.result == "PASSED" for r in rows)
    ids = {r.id for r in rows}
    # External Filing-Rule ids where mapped; internal NC-S** otherwise.
    assert "FR 1.7.1" in ids  # missing filing indicator
    assert "FR 3.2(b)" in ids  # percentage-as-ratio
    assert any(i.startswith("NC-S") for i in ids)
    assert all(r.source == "structural" for r in rows)


def test_register_failed_structural_row_carries_location_and_detail() -> None:
    findings = [
        _f("UNRESOLVED_FACT", template_code="C_67.00.a", row_code="9999",
           column_code="0010", file="facts.xlsx", row=5),
    ]
    rows = build_register(findings, None)
    unresolved = [r for r in rows if r.id == "NC-S01"]
    # One FAILED row (the finding), no separate PASSED row for that rule.
    assert len(unresolved) == 1
    row = unresolved[0]
    assert row.result == "FAILED"
    assert row.template == "C_67.00.a"
    assert "C_67.00.a" in row.data_evaluated
    assert row.detail == "UNRESOLVED_FACT message"


def test_register_merges_formula_rules() -> None:
    formula = {
        "status": "executed",
        "loaded": 3,
        "evaluated": 2,
        "satisfied": 1,
        "unsatisfied": 1,
        "deactivated": ["v6272_m", "v23336_m"],
        "rules": [
            {"rule_id": "v16053_m", "assertion_type": "Value Assertion",
             "satisfied": 0, "not_satisfied": 1, "result": "FAILED",
             "values": "{C_72.00.a,0010,0010,} 57621 >= 66241",
             "message": "v16053_m: ... Fails because 57621 >= 66241 is not true."},
            {"rule_id": "v7681_s", "assertion_type": "Value Assertion",
             "satisfied": 5, "not_satisfied": 0, "result": "PASSED",
             "values": None, "message": None},
        ],
    }
    rows = build_register([], formula)
    formula_rows = [r for r in rows if r.source == "formula"]
    assert {r.id for r in formula_rows} == {"v16053_m", "v7681_s"}
    failed = next(r for r in formula_rows if r.id == "v16053_m")
    assert failed.result == "FAILED"
    assert failed.template == "C_72.00.a"  # extracted from the cell ref
    passed = next(r for r in formula_rows if r.id == "v7681_s")
    assert passed.result == "PASSED"
    assert "5 satisfied" in passed.detail


def test_report_html_mirrors_register_and_formula_note() -> None:
    findings = [_f("UNRESOLVED_FACT", template_code="C_67.00.a")]
    formula = {
        "status": "executed", "loaded": 100, "evaluated": 2,
        "satisfied": 1, "unsatisfied": 1, "deactivated": ["v6272_m"],
        "rules": [
            {"rule_id": "v16053_m", "assertion_type": "Value Assertion",
             "satisfied": 0, "not_satisfied": 1, "result": "FAILED",
             "values": "57621 >= 66241", "message": "Fails."},
        ],
    }
    register = build_register(findings, formula)
    html = build_report_html(
        identity=[("Run", "#42"), ("Suite", "LCR")],
        register=register,
        formula=formula,
    )
    # Three sections by rule family (severity never sections).
    assert "Formula validations" in html or "Formula:" in html
    assert "Filing &amp; structural checks" in html or "Structural:" in html
    assert "Informational" in html
    assert "FR 1.7.1" in html  # a structural rule id
    assert "v16053_m" in html  # a formula rule id
    assert "UNRESOLVED_FACT message" in html
    assert "Not submittable" in html  # has a FAILED row
    # Explicit formula counts + per-section headline + a severity badge.
    assert "100 rules loaded, 2 evaluated" in html
    assert "Formula:" in html and "Structural:" in html
    assert "Blocking" in html  # severity badge on the blocking structural row
    assert "v6272_m" in html  # deactivated note


def test_report_html_formula_not_run() -> None:
    html = build_report_html(
        identity=[("Run", "#1")], register=build_register([], None), formula=None
    )
    assert "has not run" in html
    assert "Submittable" in html  # no failed rows


def test_report_formula_section_never_green_when_zero_evaluated() -> None:
    # Formula ran but evaluated nothing → the section says so loudly, never an
    # implied green pass.
    formula = {
        "status": "executed", "loaded": 500, "evaluated": 0,
        "satisfied": 0, "unsatisfied": 0, "rules": [], "deactivated": [],
        "note": None,
    }
    html = build_report_html(
        identity=[("Run", "#7")], register=build_register([], formula),
        formula=formula,
    )
    assert "evaluated 0 rules" in html
    assert "not a pass" in html
