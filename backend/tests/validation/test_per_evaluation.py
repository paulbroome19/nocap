"""Per-evaluation detail: the adapter retains individual failing evaluations."""

from __future__ import annotations

import random

from app.validation.arelle_adapter import rule_results_from_records

# One rule (v16053_m) that failed on THREE distinct cells, plus its trace giving
# 2 satisfied / 3 not-satisfied. Each failing cell is a separate message record
# with its own cell ref + compared values.
_RECORDS = [
    {"code": "formula:trace", "level": "info", "message": {"text":
        "Value Assertion v16053_m_0 evaluations : 2 satisfied, 3 not satisfied "
        "- http://.../vr-v16053_m.xml"}},
    {"code": "message:v16053_m_0", "level": "warning", "message": {"text":
        "v16053_m_0: {C_72.00.a,0010,0010,} >= {C_72.00.a,0020,0010,} "
        "Fails because 100 >= 200 is not true."}},
    {"code": "message:v16053_m_1", "level": "warning", "message": {"text":
        "v16053_m_1: {C_72.00.a,0030,0010,} >= {C_72.00.a,0040,0010,} "
        "Fails because 5 >= 9 is not true."}},
    {"code": "message:v16053_m_2", "level": "warning", "message": {"text":
        "v16053_m_2: {C_72.00.a,0050,0010,} >= {C_72.00.a,0060,0010,} "
        "Fails because 1 >= 7 is not true."}},
]


def test_all_failing_evaluations_retained() -> None:
    results, _ = rule_results_from_records(_RECORDS, deactivated_rules=set())
    rule = next(r for r in results if r.rule_id == "v16053_m")
    assert (rule.satisfied, rule.not_satisfied) == (2, 3)
    # Three individual failing evaluations retained (not collapsed to one).
    assert len(rule.evaluations) == 3
    cells = {
        (e["template_code"], e["row_code"], e["column_code"])
        for e in rule.evaluations
    }
    assert cells == {
        ("C_72.00.a", "0010", "0010"),
        ("C_72.00.a", "0030", "0010"),
        ("C_72.00.a", "0050", "0010"),
    }
    # Each carries the compared values.
    assert {e["values"] for e in rule.evaluations} == {"100 >= 200", "5 >= 9", "1 >= 7"}


def test_evaluations_are_order_independent() -> None:
    def evals(recs):
        results, _ = rule_results_from_records(recs, deactivated_rules=set())
        rule = next(r for r in results if r.rule_id == "v16053_m")
        return [(e["message"], e["values"]) for e in rule.evaluations]

    baseline = evals(_RECORDS)
    for _ in range(6):
        shuffled = _RECORDS[:]
        random.shuffle(shuffled)
        assert evals(shuffled) == baseline


def test_build_formula_summary_persists_evaluations_and_severity() -> None:
    from app.validation.arelle_adapter import FormulaRun, RuleResult
    from app.workflows.service import _build_formula_summary

    rr = RuleResult(
        rule_id="v16053_m", assertion_type="Value Assertion",
        satisfied=2, not_satisfied=3, result="FAILED",
        values="100 >= 200", message="…",
        evaluations=[{"message": "m", "values": "100 >= 200",
                      "template_code": "C_72.00.a", "row_code": "0010",
                      "column_code": "0010"}],
    )
    run = FormulaRun(findings=[], rule_results=[rr], available=True, loaded=1)
    summary = _build_formula_summary(run, {"v16053_m": "error"})
    rule = summary["rules"][0]
    assert rule["evaluations"] and rule["evaluations"][0]["values"] == "100 >= 200"
    assert rule["severity"] == "error"
    assert rule["blocking"] is True
