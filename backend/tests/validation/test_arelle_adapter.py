"""Arelle adapter — the log→findings mapping (canned output; no package needed)."""

from __future__ import annotations

from pathlib import Path

from app.validation.arelle_adapter import (
    ArelleFormulaValidator,
    eurofiling_package,
    findings_from_arelle_records,
    load_deactivated_rules,
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


def test_eurofiling_package_builds_valid_zip(tmp_path: Path) -> None:
    import zipfile

    zip_path = eurofiling_package(tmp_path)
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert any(n.endswith("META-INF/taxonomyPackage.xml") for n in names)
    assert any(n.endswith("ext/model.xsd") for n in names)
