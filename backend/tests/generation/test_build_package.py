"""Deterministic xBRL-CSV package builder."""

from __future__ import annotations

import pytest

from app.core.errors import ValidationError
from app.generation.schemas import FilingIndicatorSpec
from app.generation.service import (
    build_package,
    entry_point_url,
    module_version_6,
)
from tests.generation._helpers import fi, metadata, open_zip, read_member, resolver

# C_73.00.a: two monetary cells; C_76.00.a: a percentage cell.
_MAP = {
    ("C_73.00.a", "0010", "0010"): (5436020, "m"),
    ("C_73.00.a", "0020", "0010"): (5436019, "m"),
    ("C_76.00.a", "0030", "0010"): (5435202, "p"),
}
_FACTS = [
    fi("C_73.00.a", "0010", "0010", "4500000"),
    fi("C_73.00.a", "0020", "0010", "1250000"),
    fi("C_76.00.a", "0030", "0010", "1.32"),
]


def _build():
    return build_package(_FACTS, metadata(), resolve=resolver(_MAP))


def test_filename_follows_eba_convention() -> None:
    pkg = _build()
    assert pkg.filename == (
        "5299001234567890ABCD.CON_DE_COREP030300_COREPLCRDA"
        "_2025-12-31_20260101000000000.zip"
    )


def test_module_version_6() -> None:
    assert module_version_6("3.3.0") == "030300"
    assert module_version_6("4.0.0") == "040000"
    assert module_version_6("1.0.1") == "010001"


def test_entry_point_derived_and_overridable() -> None:
    assert entry_point_url(metadata()) == (
        "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/corep/4.2/mod/corep_lcr_da.json"
    )
    assert entry_point_url(metadata(entry_point_url="http://x/y.json")) == "http://x/y.json"


def test_entry_point_uses_framework_version_not_dpm_revision() -> None:
    """A DPM revision code (4.2.1) must resolve to the framework taxonomy entry
    point (4.2) — the taxonomy is versioned at the framework level. Using 4.2.1
    would yield xbrlce:unresolvableBaseMetadataFile against the 4.2 package."""
    from app.generation.service import framework_taxonomy_version

    assert framework_taxonomy_version("4.2.1") == "4.2"
    assert framework_taxonomy_version("4.2.1.0") == "4.2"
    assert framework_taxonomy_version("4.2") == "4.2"
    assert entry_point_url(metadata(taxonomy_version="4.2.1")) == (
        "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/corep/4.2/mod/corep_lcr_da.json"
    )


def test_package_structure() -> None:
    pkg = _build()
    root = pkg.filename[:-4]
    names = set(open_zip(pkg.content).namelist())
    assert names == {
        f"{root}/META-INF/reportPackage.json",
        f"{root}/reports/report.json",
        f"{root}/reports/parameters.csv",
        f"{root}/reports/FilingIndicators.csv",
        f"{root}/reports/c_73.00.a.csv",
        f"{root}/reports/c_76.00.a.csv",
    }


def test_template_csv_rows_sorted_by_datapoint_crlf() -> None:
    raw = read_member(_build().content, "c_73.00.a.csv")
    assert raw == (
        b"datapoint,factValue\r\n"
        b"dp5436019,1250000\r\n"
        b"dp5436020,4500000\r\n"
    )


def test_parameters_conditional_on_datatypes() -> None:
    text = read_member(_build().content, "parameters.csv").decode()
    lines = text.split("\r\n")
    assert lines[0] == "name,value"
    assert "entityID,rs:5299001234567890ABCD.CON" in lines
    assert "refPeriod,2025-12-31" in lines
    assert "baseCurrency,iso4217:EUR" in lines  # monetary present
    assert "decimalsMonetary,-3" in lines
    assert "decimalsPercentage,4" in lines  # percentage present
    assert not any(line.startswith("decimalsInteger") for line in lines)
    assert not any(line.startswith("decimalsDecimal") for line in lines)


def test_parameters_omit_currency_when_no_monetary() -> None:
    facts = [fi("C_76.00.a", "0030", "0010", "1.32")]
    pkg = build_package(facts, metadata(), resolve=resolver(_MAP))
    text = read_member(pkg.content, "parameters.csv").decode()
    assert "baseCurrency" not in text
    assert "decimalsMonetary" not in text
    assert "decimalsPercentage,4" in text


def test_filing_indicators_sorted() -> None:
    md = metadata(
        filing_indicators=[
            FilingIndicatorSpec(template_code="C_76.00.a", reported=True),
            FilingIndicatorSpec(template_code="C_73.00.a", reported=False),
        ]
    )
    pkg = build_package(_FACTS, md, resolve=resolver(_MAP))
    assert read_member(pkg.content, "FilingIndicators.csv") == (
        b"templateID,reported\r\nC_73.00.a,false\r\nC_76.00.a,true\r\n"
    )


def test_report_json_extends_entry_point() -> None:
    import json

    data = json.loads(read_member(_build().content, "report.json"))
    assert data["documentInfo"]["documentType"] == "https://xbrl.org/2021/xbrl-csv"
    assert data["documentInfo"]["extends"] == [
        "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/corep/4.2/mod/corep_lcr_da.json"
    ]


def test_deterministic_byte_identical() -> None:
    assert _build().content == _build().content


def test_unresolved_fact_raises_with_details() -> None:
    facts = [fi("C_99.99", "0010", "0010", "1")]
    with pytest.raises(ValidationError) as exc:
        build_package(facts, metadata(), resolve=resolver(_MAP))
    assert exc.value.details and exc.value.details[0]["template"] == "C_99.99"


def test_non_strict_skips_unresolved_and_keeps_first() -> None:
    facts = [
        fi("C_73.00.a", "0010", "0010", "4500000"),  # resolves
        fi("C_99.99", "0010", "0010", "1"),  # unresolved -> skipped
        fi("C_73.00.a", "0010", "0010", "9999999"),  # dup -> first kept
    ]
    pkg = build_package(facts, metadata(), resolve=resolver(_MAP), strict=False)
    assert pkg.templates == ["C_73.00.a"]
    assert read_member(pkg.content, "c_73.00.a.csv") == (
        b"datapoint,factValue\r\ndp5436020,4500000\r\n"
    )


def test_conflicting_datapoint_raises() -> None:
    facts = [
        fi("C_73.00.a", "0010", "0010", "1"),
        fi("C_73.00.a", "0010", "0010", "2"),
    ]
    with pytest.raises(ValidationError):
        build_package(facts, metadata(), resolve=resolver(_MAP))


def test_csv_value_escaping() -> None:
    mapping = {("C_73.00.a", "0010", "0010"): (100, "s")}
    facts = [fi("C_73.00.a", "0010", "0010", 'a,b"c')]
    pkg = build_package(facts, metadata(), resolve=resolver(mapping))
    assert read_member(pkg.content, "c_73.00.a.csv") == (
        b'datapoint,factValue\r\ndp100,"a,b""c"\r\n'
    )
