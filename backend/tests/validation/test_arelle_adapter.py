"""Arelle adapter — the log→findings mapping (canned output; no package needed)."""

from __future__ import annotations

from pathlib import Path

from app.validation.arelle_adapter import (
    ArelleFormulaValidator,
    eurofiling_package,
    expand_taxonomy_packages,
    findings_from_arelle_records,
    load_deactivated_rules,
    rule_results_from_records,
    unavailable_finding,
)
from app.validation.models import Severity, ValidationPhase

# Canned Arelle getJson()-style records (as observed in the spike).
_RECORDS = [
    {"code": "info", "level": "info", "message": {"text": "loaded in 7s"}},
    {
        "code": "message:v16053_m_0",
        "level": "warning",
        "message": {
            "text": "v16053_m_0: {D_02.00.a,0060,0100,} >= {D_02.00.a,0070,0100,} "
            "Fails because 57621 >= 66241 is not true."
        },
    },
    # same rule firing on another fact -> collapses to one finding
    {
        "code": "message:v16053_m_6",
        "level": "warning",
        "message": {"text": "v16053_m_6: {D_02.00.a,0060,0150,} >= ... Fails."},
    },
    # deactivated rule -> dropped
    {
        "code": "message:v6272_m_0",
        "level": "error",
        "message": {"text": "v6272_m_0: deactivated rule"},
    },
    # message given as a plain string; error severity
    {
        "code": "message:v89377_m_8",
        "level": "error",
        "message": "v89377_m_8: {D_07.00.a,0260,0030,} <= {D_07.00.a,0240,0030,} "
        "Fails because 74967 <= 61651 is not true.",
    },
]


def test_maps_records_to_findings() -> None:
    findings = findings_from_arelle_records(
        _RECORDS, deactivated_rules={"v6272_m"}
    )
    by_code = {f.code: f for f in findings}
    assert set(by_code) == {"v16053_m", "v89377_m"}  # deactivated dropped, dedup

    warn = by_code["v16053_m"]
    assert warn.severity is Severity.warning
    assert warn.phase is ValidationPhase.formula
    assert (warn.template_code, warn.row_code, warn.column_code) == (
        "D_02.00.a", "0060", "0100",
    )

    err = by_code["v89377_m"]
    assert err.severity is Severity.error
    assert err.template_code == "D_07.00.a" and err.row_code == "0260"


def test_findings_are_order_independent() -> None:
    """Arelle emits per-fact messages in a non-deterministic order; extraction
    must be deterministic (same findings regardless of record order) — this is
    what makes cached and uncached validations produce identical findings."""
    import random

    # A rule firing on three facts, plus another rule.
    records = [
        {"code": "message:v16053_m_2", "level": "warning", "message": {"text":
            "v16053_m: {D_02.00.a,0060,0300,} >= x Fails because 3 >= 9."}},
        {"code": "message:v16053_m_0", "level": "warning", "message": {"text":
            "v16053_m: {D_02.00.a,0060,0100,} >= x Fails because 1 >= 9."}},
        {"code": "message:v16053_m_1", "level": "warning", "message": {"text":
            "v16053_m: {D_02.00.a,0060,0200,} >= x Fails because 2 >= 9."}},
        {"code": "message:v89377_m_0", "level": "error", "message": {"text":
            "v89377_m: {D_07.00.a,0260,0030,} <= y Fails because 7 <= 6."}},
    ]

    def canon(recs):
        f = findings_from_arelle_records(recs, deactivated_rules=set())
        rr, loaded = rule_results_from_records(recs, deactivated_rules=set())
        return (
            [(x.code, x.message, x.row_code, x.column_code) for x in f],
            [(x.rule_id, x.result, x.values, x.message) for x in rr],
        )

    baseline = canon(records)
    for _ in range(8):
        shuffled = records[:]
        random.shuffle(shuffled)
        assert canon(shuffled) == baseline  # identical regardless of order


def test_deactivated_default_list() -> None:
    rules = load_deactivated_rules()
    assert "v6272_m" in rules and "v23336_m" in rules
    assert "v99999_m" in load_deactivated_rules({"v99999_m"})


def test_unavailable_finding_is_info() -> None:
    f = unavailable_finding("Arelle not installed")
    assert f.severity is Severity.info
    assert f.code == "FORMULA_VALIDATION_UNAVAILABLE"
    assert f.phase is ValidationPhase.formula


def test_validate_without_taxonomy_returns_unavailable(tmp_path: Path) -> None:
    validator = ArelleFormulaValidator(cache_dir=tmp_path)
    findings = validator.validate(tmp_path / "pkg.zip", taxonomy_packages=[])
    assert len(findings) == 1
    assert findings[0].code == "FORMULA_VALIDATION_UNAVAILABLE"


# Canned records in Arelle's REAL --formulaSatisfiedAsser/UnsatisfiedAsser
# format (verified against a live 4.2 formula run — see PR notes).
_RULE_RECORDS = [
    # A rule that evaluated and passed (aggregated over two instances → 5/0).
    {"code": "formula:trace", "level": "info", "message": {"text":
        "Value Assertion v7681_s_15 evaluations : 3 satisfied, 0 not satisfied "
        "- http://.../vr-v7681_s.xml"}},
    {"code": "formula:trace", "level": "info", "message": {"text":
        "Value Assertion v7681_s_16 evaluations : 2 satisfied, 0 not satisfied "
        "- http://.../vr-v7681_s.xml"}},
    # A rule that evaluated and failed, with its unsatisfied message.
    {"code": "formula:trace", "level": "info", "message": {"text":
        "Value Assertion v16053_m_0 evaluations : 0 satisfied, 1 not satisfied "
        "- http://.../vr-v16053_m.xml"}},
    {"code": "message:v16053_m_0", "level": "warning", "message": {"text":
        "v16053_m_0: {D_02.00.a,0060,0100,} >= {D_02.00.a,0070,0100,} "
        "Fails because 57621 >= 66241 is not true."}},
    # Loaded but not evaluated against this submission's data (0/0).
    {"code": "formula:trace", "level": "info", "message": {"text":
        "Value Assertion v9999_m_0 evaluations : 0 satisfied, 0 not satisfied "
        "- http://.../vr-v9999_m.xml"}},
    # Deactivated rule → dropped entirely.
    {"code": "formula:trace", "level": "info", "message": {"text":
        "Value Assertion v6272_m_0 evaluations : 0 satisfied, 5 not satisfied "
        "- http://.../vr-v6272_m.xml"}},
]


def test_rule_results_capture_satisfied_and_failed() -> None:
    results, loaded = rule_results_from_records(
        _RULE_RECORDS, deactivated_rules={"v6272_m"}
    )
    # v6272_m excluded; v7681_s, v16053_m, v9999_m traced.
    assert loaded == 3
    by_id = {r.rule_id: r for r in results}
    # Only the two rules that actually evaluated appear as results.
    assert set(by_id) == {"v7681_s", "v16053_m"}

    passed = by_id["v7681_s"]
    assert passed.result == "PASSED"
    assert (passed.satisfied, passed.not_satisfied) == (5, 0)  # aggregated

    failed = by_id["v16053_m"]
    assert failed.result == "FAILED"
    assert failed.not_satisfied == 1
    assert failed.values == "57621 >= 66241"  # extracted comparison
    assert "not true" in (failed.message or "")

    # Failed rules sort first.
    assert results[0].rule_id == "v16053_m"


def test_validate_detailed_unavailable_without_taxonomy(tmp_path: Path) -> None:
    v = ArelleFormulaValidator(cache_dir=tmp_path)
    run = v.validate_detailed(tmp_path / "pkg.zip", taxonomy_packages=[])
    assert run.available is False
    assert run.rule_results == []
    assert run.findings[0].code == "FORMULA_VALIDATION_UNAVAILABLE"
    assert "v6272_m" in run.deactivated


def test_expand_taxonomy_packages_extracts_inner_zips(tmp_path: Path) -> None:
    import io
    import zipfile

    def _pkg(entries: dict) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for name, data in entries.items():
                zf.writestr(name, data)
        return buf.getvalue()

    # A real taxonomy package (has META-INF/taxonomyPackage.xml) passes through.
    real = tmp_path / "real.zip"
    real.write_bytes(_pkg({"META-INF/taxonomyPackage.xml": "<x/>"}))
    # A container of inner package zips is expanded.
    inner = _pkg({"META-INF/taxonomyPackage.xml": "<x/>"})
    container = tmp_path / "container.zip"
    container.write_bytes(
        _pkg({"EBA_Dictionary.zip": inner, "notes.pdf": "pdf"})
    )

    out = expand_taxonomy_packages([real, container], tmp_path / "cache")
    names = sorted(p.name for p in out)
    assert names == ["EBA_Dictionary.zip", "real.zip"]


def test_eurofiling_package_builds_valid_zip(tmp_path: Path) -> None:
    import zipfile

    zip_path = eurofiling_package(tmp_path)
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert any(n.endswith("META-INF/taxonomyPackage.xml") for n in names)
    assert any(n.endswith("ext/model.xsd") for n in names)
