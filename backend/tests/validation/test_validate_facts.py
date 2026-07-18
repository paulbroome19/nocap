"""Phase 1 (facts) validation checks."""

from __future__ import annotations

from datetime import date

from app.validation.models import Severity
from app.validation.service import validate_facts
from tests.validation._helpers import fact, indicator, resolver

# datapoint map: monetary dp900, percentage dp901.
_MAP = {
    ("C_73.00.a", "0010", "0010"): (900, "m"),
    ("C_73.00.a", "0020", "0010"): (901, "p"),
}
_MODULE = {"C_73.00.a", "C_74.00.a"}


def _run(facts, indicators, **over):
    kw = dict(
        facts=facts,
        resolve=resolver(_MAP),
        module_templates=_MODULE,
        open_templates=set(),
        filing_indicators=indicators,
        fact_file_name="facts.xlsx",
        entity_id="5299001234567890ABCD",
        ref_period=date(2025, 12, 31),
    )
    kw.update(over)
    return validate_facts(**kw)


def _codes(findings, severity=None):
    return [
        f.code for f in findings if severity is None or f.severity is severity
    ]


def test_clean_facts_have_no_findings() -> None:
    facts = [fact("C_73.00.a", "0010", "0010", "1000")]
    findings = _run(facts, [indicator("C_73.00.a")])
    assert findings == []


def test_unresolved_fact_reports_row_location() -> None:
    facts = [fact("C_73.00.a", "9999", "0010", "1", src_row=7)]
    findings = _run(facts, [indicator("C_73.00.a")])
    unresolved = [f for f in findings if f.code == "UNRESOLVED_FACT"]
    assert len(unresolved) == 1
    f = unresolved[0]
    assert f.severity is Severity.error
    assert f.file == "facts.xlsx" and f.sheet == "facts" and f.row == 7
    assert f.row_code == "9999" and f.column_code == "0010"


def test_datatype_mismatch_monetary() -> None:
    facts = [fact("C_73.00.a", "0010", "0010", "not-a-number")]
    findings = _run(facts, [indicator("C_73.00.a")])
    assert "DATATYPE_MISMATCH" in _codes(findings, Severity.error)


def test_percentage_not_ratio_warns() -> None:
    facts = [fact("C_73.00.a", "0020", "0010", "9.31")]  # should be 0.0931
    findings = _run(facts, [indicator("C_73.00.a")])
    warnings = [f for f in findings if f.code == "PERCENTAGE_NOT_RATIO"]
    assert warnings and warnings[0].severity is Severity.warning


def test_duplicate_fact() -> None:
    facts = [
        fact("C_73.00.a", "0010", "0010", "1000"),
        fact("C_73.00.a", "0010", "0010", "2000", src_row=3),
    ]
    findings = _run(facts, [indicator("C_73.00.a")])
    dups = [f for f in findings if f.code == "DUPLICATE_FACT"]
    assert len(dups) == 1 and dups[0].row == 3


def test_missing_filing_indicator() -> None:
    facts = [fact("C_73.00.a", "0010", "0010", "1000")]
    findings = _run(facts, [])  # no indicator for a template with facts
    assert "MISSING_FILING_INDICATOR" in _codes(findings, Severity.error)


def test_empty_filing_indicator_warns() -> None:
    # Indicator says C_74.00.a reported, but there are no facts for it.
    facts = [fact("C_73.00.a", "0010", "0010", "1000")]
    findings = _run(
        facts, [indicator("C_73.00.a"), indicator("C_74.00.a")]
    )
    empty = [f for f in findings if f.code == "EMPTY_FILING_INDICATOR"]
    assert empty and empty[0].severity is Severity.warning
    assert empty[0].template_code == "C_74.00.a"


def test_indicator_not_in_module() -> None:
    facts = [fact("C_73.00.a", "0010", "0010", "1000")]
    findings = _run(
        facts, [indicator("C_73.00.a"), indicator("C_99.99")]  # not in module
    )
    bad = [f for f in findings if f.code == "INDICATOR_NOT_IN_MODULE"]
    assert bad and bad[0].template_code == "C_99.99"


def test_open_table_unsupported() -> None:
    facts = [
        fact("C_77.00", "0010", "0010", "1"),
        fact("C_77.00", "0020", "0010", "2", src_row=3),  # same template again
        fact("C_73.00.a", "0010", "0010", "1000", src_row=4),
    ]
    findings = _run(
        facts, [indicator("C_73.00.a")], open_templates={"C_77.00"}
    )
    open_findings = [f for f in findings if f.code == "OPEN_TABLE_UNSUPPORTED"]
    # One finding per open template (deduped), with a clear message.
    assert len(open_findings) == 1
    assert open_findings[0].template_code == "C_77.00"
    assert "not supported in v1" in open_findings[0].message
    # The open-table facts are not also reported as unresolved.
    assert not [f for f in findings if f.code == "UNRESOLVED_FACT"]


def test_missing_parameters() -> None:
    facts = [fact("C_73.00.a", "0010", "0010", "1000")]
    findings = _run(facts, [indicator("C_73.00.a")], entity_id="", ref_period=None)
    assert _codes(findings, Severity.error).count("PARAM_MISSING") == 2
