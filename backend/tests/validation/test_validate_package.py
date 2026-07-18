"""Phase 2 (package) validation checks — broken-fixture driven."""

from __future__ import annotations

from app.validation.models import Severity
from app.validation.service import validate_package
from tests.generation._helpers import metadata, resolver
from tests.validation._helpers import clean_members, make_zip

# A well-formed package filename and its root folder.
FN = (
    "5299001234567890ABCD.CON_DE_COREP030300_COREPLCRDA"
    "_2025-12-31_20260101000000000.zip"
)
ROOT = FN[:-4]

_PARAMS = [
    ["name", "value"],
    ["entityID", "rs:5299001234567890ABCD.CON"],
    ["refPeriod", "2025-12-31"],
    ["baseCurrency", "iso4217:EUR"],
    ["decimalsMonetary", "-3"],
]
_INDICATORS = [["templateID", "reported"], ["C_73.00.a", "true"]]
_TEMPLATE = [["datapoint", "factValue"], ["dp900", "1000"]]


def _csvs(**over):
    csvs = {
        "parameters.csv": _PARAMS,
        "FilingIndicators.csv": _INDICATORS,
        "c_73.00.a.csv": _TEMPLATE,
    }
    csvs.update(over)
    return csvs


def _validate(members: dict, *, filename=FN, root=ROOT, datatypes=None):
    return validate_package(
        package_bytes=make_zip(root, members),
        package_filename=filename,
        datatypes_present={"m"} if datatypes is None else datatypes,
    )


def _codes(findings, severity=Severity.error):
    return [f.code for f in findings if f.severity is severity]


def test_clean_generated_package_only_info() -> None:
    """A real generated package validates with only the info finding."""
    from app.generation.schemas import FactInput
    from app.generation.service import build_package

    facts = [
        FactInput(
            template_code="C_73.00.a", row_code="0010", column_code="0010",
            value="1000",
        )
    ]
    pkg = build_package(
        facts,
        metadata(),
        resolve=resolver({("C_73.00.a", "0010", "0010"): (900, "m")}),
    )
    findings = validate_package(
        package_bytes=pkg.content,
        package_filename=pkg.filename,
        datatypes_present={"m"},
    )
    assert _codes(findings, Severity.error) == []
    assert _codes(findings, Severity.info) == ["ENTRY_POINT_UNVERIFIED"]


def test_missing_member() -> None:
    csvs = _csvs()
    del csvs["parameters.csv"]
    findings = _validate(clean_members(csvs))
    assert "PACKAGE_LAYOUT" in _codes(findings)


def test_wrong_root_folder() -> None:
    findings = _validate(clean_members(_csvs()), root="WRONGROOT")
    assert "PACKAGE_LAYOUT" in _codes(findings)


def test_bad_filename() -> None:
    findings = _validate(clean_members(_csvs()), filename="not-a-valid-name.zip")
    assert "FILENAME_CONVENTION" in _codes(findings)


def test_empty_header_cell() -> None:
    tmpl = [["datapoint", ""], ["dp900", "1000"]]
    findings = _validate(clean_members(_csvs(**{"c_73.00.a.csv": tmpl})))
    assert "EMPTY_HEADER" in _codes(findings)


def test_inconsistent_field_count() -> None:
    tmpl = [["datapoint", "factValue"], ["dp900", "1000", "extra"]]
    findings = _validate(clean_members(_csvs(**{"c_73.00.a.csv": tmpl})))
    assert "INCONSISTENT_FIELD_COUNT" in _codes(findings)


def test_forbidden_special_value() -> None:
    tmpl = [["datapoint", "factValue"], ["dp900", "#empty"]]
    findings = _validate(clean_members(_csvs(**{"c_73.00.a.csv": tmpl})))
    special = [f for f in findings if f.code == "FORBIDDEN_SPECIAL_VALUE"]
    assert special and special[0].row == 2


def test_decimals_suffix() -> None:
    tmpl = [["datapoint", "factValue"], ["dp900", "1000d-4"]]
    findings = _validate(clean_members(_csvs(**{"c_73.00.a.csv": tmpl})))
    assert "DECIMALS_SUFFIX" in _codes(findings)


def test_not_crlf() -> None:
    members = clean_members(_csvs())
    # Rewrite one CSV with LF-only endings.
    members["reports/c_73.00.a.csv"] = b"datapoint,factValue\ndp900,1000\n"
    findings = _validate(members)
    assert "NOT_CRLF" in _codes(findings)


def test_key_column_empty() -> None:
    tmpl = [["datapoint", "factValue", "qEEA"], ["dp900", "1000", ""]]
    findings = _validate(clean_members(_csvs(**{"c_73.00.a.csv": tmpl})))
    assert "KEY_COLUMN_EMPTY" in _codes(findings)


def test_param_wrongly_included() -> None:
    # baseCurrency present but no monetary fact -> must be omitted.
    findings = _validate(clean_members(_csvs()), datatypes={"p"})
    assert "PARAM_WRONGLY_INCLUDED" in _codes(findings)


def test_negative_indicator_csv() -> None:
    # c_73.00.a.csv is present but its filing indicator is negative (v5.8 rule 6).
    indicators = [["templateID", "reported"], ["C_73.00.a", "false"]]
    findings = _validate(clean_members(_csvs(**{"FilingIndicators.csv": indicators})))
    assert "NEGATIVE_INDICATOR_CSV" in _codes(findings)


def test_param_missing() -> None:
    params = [r for r in _PARAMS if r[0] != "baseCurrency"]
    findings = _validate(clean_members(_csvs(**{"parameters.csv": params})))
    assert "PARAM_MISSING" in _codes(findings)


def test_unreadable_zip() -> None:
    findings = validate_package(
        package_bytes=b"not a zip",
        package_filename=FN,
        datatypes_present=set(),
    )
    assert "PACKAGE_UNREADABLE" in _codes(findings)
