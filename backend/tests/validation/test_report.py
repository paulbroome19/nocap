"""Validation report substance: checks inventory + HTML report content."""

from __future__ import annotations

from app.validation import checks
from app.validation.models import Severity, ValidationPhase
from app.validation.report import build_report_html
from app.validation.schemas import Finding


def _f(code, severity=Severity.error, phase=ValidationPhase.pre_generation, **loc):
    return Finding(
        severity=severity, phase=phase, code=code, message=f"{code} message", **loc
    )


def test_structural_results_clean_run_all_pass() -> None:
    results = {r.key: r for r in checks.structural_check_results([])}
    # Every catalogued check appears and passes on a clean run.
    assert {c.key for c in checks.STRUCTURAL_CHECKS} <= set(results)
    assert all(r.status == "pass" for r in results.values())


def test_structural_results_map_codes_to_categories() -> None:
    findings = [
        _f("UNRESOLVED_FACT"),
        _f("DUPLICATE_FACT"),
        _f("PERCENTAGE_NOT_RATIO", severity=Severity.warning),
        _f("ENTRY_POINT_UNVERIFIED", severity=Severity.info,
           phase=ValidationPhase.post_generation),
        # a formula finding must be ignored by the structural inventory
        _f("v16053_m", severity=Severity.warning, phase=ValidationPhase.formula),
    ]
    results = {r.key: r for r in checks.structural_check_results(findings)}
    assert results["datapoint_resolution"].status == "fail"
    assert results["datapoint_resolution"].errors == 1
    assert results["duplicate_facts"].status == "fail"
    assert results["datatype_conformance"].status == "warning"
    assert results["datatype_conformance"].warnings == 1
    assert results["entry_point"].status == "note"
    assert results["entry_point"].infos == 1
    # Filing-indicator check had no findings -> pass.
    assert results["filing_indicators"].status == "pass"


def test_formula_rule_ids_dedupe_and_exclude_marker() -> None:
    findings = [
        _f("v16053_m", severity=Severity.warning, phase=ValidationPhase.formula),
        _f("v16053_m", severity=Severity.warning, phase=ValidationPhase.formula),
        _f("v89377_m", severity=Severity.error, phase=ValidationPhase.formula),
        _f("FORMULA_VALIDATION_UNAVAILABLE", severity=Severity.info,
           phase=ValidationPhase.formula),
    ]
    assert checks.formula_rule_ids(findings) == ["v16053_m", "v89377_m"]


def test_report_html_carries_identity_checks_and_findings() -> None:
    findings = [
        _f("UNRESOLVED_FACT", template_code="C_67.00.a", row_code="9999",
           column_code="0010", file="facts.xlsx", row=5),
        _f("v89377_m", severity=Severity.error, phase=ValidationPhase.formula),
    ]
    html = build_report_html(
        identity=[
            ("Run", "#42"),
            ("Suite", "LCR (COREP_LCR_DA)"),
            ("Entity", "Meridian · 529900X.CON"),
            ("Taxonomy release", "4.2"),
        ],
        structural_checks=checks.structural_check_results(findings),
        formula={
            "status": "executed",
            "unsatisfied": 1,
            "unsatisfied_rule_ids": ["v89377_m"],
            "deactivated": ["v23336_m", "v6272_m"],
            "note": None,
        },
        findings=findings,
    )
    # Identity
    assert "#42" in html and "LCR (COREP_LCR_DA)" in html and "4.2" in html
    # Checks-executed inventory
    assert "Structural checks executed" in html
    assert "Datapoint resolution" in html
    # Verdict
    assert "Not submittable" in html
    # Formula section: rule ids + deactivated note
    assert "Formula validation" in html
    assert "v89377_m" in html
    assert "v6272_m" in html and "v23336_m" in html
    assert "Deactivated rules excluded" in html
    # Findings detail carries the code + location
    assert "UNRESOLVED_FACT" in html
    assert "C_67.00.a" in html


def test_report_html_formula_not_run() -> None:
    html = build_report_html(
        identity=[("Run", "#1")],
        structural_checks=checks.structural_check_results([]),
        formula=None,
        findings=[],
    )
    assert "has not run" in html
    assert "Submittable" in html  # no errors
