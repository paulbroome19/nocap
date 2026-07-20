"""NC-S19 completion guard: formula validation must actually run to completion.

A taxonomy package + scoped rules but zero evaluated rules is a loud blocking
failure (formula validation silently didn't run), and NC-S19 is only ever green
when at least one rule evaluated. Regression cover for a report that showed
NC-S19 PASSED while its own text said formula validation could not run.
"""

from __future__ import annotations

from app.validation.models import Severity, ValidationPhase
from app.validation.register import build_register
from app.workflows.models import RunStatus
from app.workflows.service import _formula_completion_finding, run_verdict


class _Run:
    def __init__(self, status=RunStatus.generated):
        self.status = status


def test_evaluated_rules_means_no_finding_ncs19_passes() -> None:
    # At least one rule evaluated → NC-S19 passes silently (no finding), so the
    # register renders NC-S19 green from the registry default.
    assert (
        _formula_completion_finding(
            evaluated=52, scoped_count=1284, package_present=True, note=None
        )
        is None
    )
    rows = build_register([], {"status": "executed", "evaluated": 52, "rules": []})
    ncs19 = next(r for r in rows if r.id == "NC-S19")
    assert ncs19.result == "PASSED"


def test_package_and_rules_but_zero_evaluated_is_blocking() -> None:
    f = _formula_completion_finding(
        evaluated=0, scoped_count=1284, package_present=True, note=None
    )
    assert f is not None
    assert f.severity is Severity.error
    assert f.phase is ValidationPhase.post_generation  # renders as the NC-S19 row
    assert f.code == "FORMULA_VALIDATION_UNAVAILABLE"
    assert "1,284" in f.message
    assert "did not run to completion" in f.message
    assert "taxonomy package" in f.message  # names the likely cause


def test_blocking_zero_evaluated_renders_ncs19_failed_and_blocks() -> None:
    f = _formula_completion_finding(
        evaluated=0, scoped_count=42, package_present=True, note=None
    )
    # Register: NC-S19 is FAILED + blocking, never a green pass.
    rows = build_register([f], {"status": "executed", "evaluated": 0, "rules": []})
    ncs19 = next(r for r in rows if r.id == "NC-S19")
    assert ncs19.result == "FAILED"
    assert ncs19.blocking is True
    # Verdict: it counts as a blocking error → not submittable.
    v = run_verdict(_Run(RunStatus.failed_validation), [f], None)
    assert v["blocking"] == 1
    assert v["submittable"] is False


def test_no_package_is_non_blocking_note_not_green() -> None:
    # No taxonomy package: formula genuinely can't run — a non-blocking note, but
    # NC-S19 is still not rendered green (it becomes a NOTE row).
    f = _formula_completion_finding(
        evaluated=0, scoped_count=5, package_present=False, note=None
    )
    assert f is not None and f.severity is Severity.info
    rows = build_register([f], None)
    ncs19 = next(r for r in rows if r.id == "NC-S19")
    assert ncs19.result == "NOTE"
    assert ncs19.blocking is False
    # Non-blocking: the run stays submittable on this alone.
    v = run_verdict(_Run(RunStatus.generated), [f], None)
    assert v["blocking"] == 0


def test_package_present_but_no_applicable_rules_is_non_blocking() -> None:
    # A package but zero scoped rules (no workbook) → can't assert rules should
    # have evaluated, so non-blocking.
    f = _formula_completion_finding(
        evaluated=0, scoped_count=0, package_present=True, note=None
    )
    assert f is not None and f.severity is Severity.info
