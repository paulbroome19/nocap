"""Banner-reasoning logic: the run verdict states blocking vs non-blocking."""

from __future__ import annotations

from dataclasses import dataclass

from app.validation.models import Severity, ValidationPhase
from app.workflows.models import RunStatus
from app.workflows.service import run_verdict


@dataclass
class _F:
    severity: Severity
    phase: ValidationPhase


@dataclass
class _Run:
    status: RunStatus


def _err(phase=ValidationPhase.pre_generation):
    return _F(Severity.error, phase)


def _warn(phase):
    return _F(Severity.warning, phase)


def test_clean_run_is_submittable() -> None:
    v = run_verdict(_Run(RunStatus.generated), [], None)
    assert v["submittable"] is True
    assert v["label"] == "Submittable"
    assert v["reasoning"] == "0 blocking errors · 0 non-blocking rule failures"


def test_non_blocking_failures_do_not_block() -> None:
    findings = [_warn(ValidationPhase.formula) for _ in range(6)]
    v = run_verdict(_Run(RunStatus.generated), findings, None)
    assert v["submittable"] is True
    assert v["blocking"] == 0
    assert v["non_blocking_failures"] == 6
    assert v["reasoning"] == "0 blocking errors · 6 non-blocking rule failures"


def test_blocking_error_makes_not_submittable() -> None:
    findings = [_err(), _warn(ValidationPhase.formula)]
    v = run_verdict(_Run(RunStatus.failed_validation), findings, None)
    assert v["submittable"] is False
    assert v["label"] == "Not submittable"
    assert v["blocking"] == 1
    assert "1 blocking error" in v["reasoning"]


def test_structural_warnings_counted_separately() -> None:
    findings = [_warn(ValidationPhase.post_generation), _warn(ValidationPhase.formula)]
    v = run_verdict(_Run(RunStatus.generated), findings, None)
    assert v["warnings"] == 1  # structural warning
    assert v["non_blocking_failures"] == 1  # formula warning
    assert "1 warning" in v["reasoning"]


def test_unknown_severity_is_surfaced() -> None:
    formula = {
        "status": "executed",
        "rules": [
            {"rule_id": "vA_m", "result": "FAILED", "severity": None},
            {"rule_id": "vB_m", "result": "FAILED", "severity": "warning"},
            {"rule_id": "vC_m", "result": "PASSED", "severity": None},
        ],
    }
    findings = [_warn(ValidationPhase.formula), _warn(ValidationPhase.formula)]
    v = run_verdict(_Run(RunStatus.generated), findings, formula)
    assert v["unknown_severity"] == 1  # only the FAILED, severity-None rule
    assert v["severity_known"] is False
    assert "1 of unknown severity" in v["reasoning"]


def test_in_progress_has_no_submittable_verdict() -> None:
    v = run_verdict(_Run(RunStatus.formula_validation_running), [], None)
    assert v["submittable"] is None
    assert v["label"] == "Validating"
