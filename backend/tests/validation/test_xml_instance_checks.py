"""The xBRL-XML structural check-set (docs/xml-notes.md §9).

A good instance from the builder passes clean; each mutation trips exactly the
expected check code.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from app.generation.schemas import FilingIndicatorSpec
from app.generation.xml_builder import build_xml_instance
from app.validation.models import Severity
from app.validation.service import validate_xml_instance
from tests.generation._helpers import (
    _Member,
    fi,
    met,
    metadata,
    xml_res,
    xml_resolver,
)

_FIS = [FilingIndicatorSpec(template_code="C_73.00.a", reported=True)]


def _good_package():
    res = xml_resolver(
        {
            ("C_73.00.a", "0010", "0010"): xml_res(
                met("mi500"),
                [_Member(_dim(), _mem())],
                "m",
            ),
            ("C_73.00.a", "0020", "0010"): xml_res(met("mi501"), [], "p"),
        }
    )
    facts = [
        fi("C_73.00.a", "0010", "0010", "1000"),
        fi("C_73.00.a", "0020", "0010", "0.5"),
    ]
    return build_xml_instance(facts, metadata(filing_indicators=_FIS), resolve=res)


def _dim():
    from tests.generation._helpers import dim

    return dim("3.4", "MHI")


def _mem():
    from tests.generation._helpers import mem

    return mem("PL", "x11")


def _xbrl_text(package_bytes: bytes) -> tuple[str, str]:
    zf = zipfile.ZipFile(io.BytesIO(package_bytes))
    name = next(n for n in zf.namelist() if n.endswith(".xbrl"))
    return name, zf.read(name).decode("utf-8")


def _rezip(name: str, xml: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(name, xml)
    return buf.getvalue()


def _by_severity(package_bytes: bytes, filename: str, sev, fis=_FIS) -> list[str]:
    findings = validate_xml_instance(
        package_bytes=package_bytes,
        package_filename=filename,
        filing_indicators=fis,
    )
    return [f.code for f in findings if f.severity is sev]


def _errors(package_bytes: bytes, filename: str, fis=_FIS) -> list[str]:
    return _by_severity(package_bytes, filename, Severity.error, fis)


def _warnings(package_bytes: bytes, filename: str, fis=_FIS) -> list[str]:
    return _by_severity(package_bytes, filename, Severity.warning, fis)


def test_good_instance_passes_clean() -> None:
    pkg = _good_package()
    findings = validate_xml_instance(
        package_bytes=pkg.content,
        package_filename=pkg.filename,
        filing_indicators=_FIS,
    )
    assert [f.code for f in findings if f.severity is Severity.error] == []
    # And no warnings either — our ids are short and non-semantic.
    assert [f.code for f in findings if f.severity is Severity.warning] == []


@pytest.mark.parametrize(
    "mutate, expected",
    [
        # Break the schemaRef href so it no longer ends .xsd.
        (lambda x: x.replace(".xsd", ".json"), "XML_SCHEMAREF"),
        # Forbidden construct: xml:base anywhere in the document.
        (
            lambda x: x.replace("<xbrli:xbrl ", '<xbrli:xbrl xml:base="/x" ', 1),
            "XML_FORBIDDEN_CONSTRUCT",
        ),
        # @precision instead of @decimals.
        (lambda x: x.replace("decimals=", "precision=", 1), "XML_DECIMALS"),
        # A second distinct entity identifier value.
        (
            lambda x: x.replace(
                "5299001234567890ABCD.CON", "OTHERENTITY.CON", 1
            ),
            "XML_SINGLE_SUBJECT",
        ),
    ],
)
def test_mutations_trip_expected_check(mutate, expected) -> None:
    pkg = _good_package()
    name, good = _xbrl_text(pkg.content)
    broken = _rezip(name, mutate(good))
    assert expected in _errors(broken, pkg.filename)


def test_duplicate_fact_detected() -> None:
    pkg = _good_package()
    name, good = _xbrl_text(pkg.content)
    # Duplicate the mi501 fact line verbatim (same element + same context).
    line = next(ln for ln in good.splitlines() if "eba_met:mi501" in ln)
    broken = _rezip(name, good.replace(line, line + "\r\n" + line, 1))
    assert "XML_DUPLICATE_FACT" in _errors(broken, pkg.filename)


def test_unused_unit_is_a_warning() -> None:
    pkg = _good_package()
    name, good = _xbrl_text(pkg.content)
    extra = '  <xbrli:unit id="uUNUSED"><xbrli:measure>xbrli:pure' \
            "</xbrli:measure></xbrli:unit>"
    broken = _rezip(
        name, good.replace("</xbrli:xbrl>", extra + "\r\n</xbrli:xbrl>", 1)
    )
    # Surplus, not a malformation → warning, not a blocking error.
    assert "XML_UNIT_HYGIENE" not in _errors(broken, pkg.filename)
    assert "XML_UNIT_HYGIENE" in _warnings(broken, pkg.filename)


def test_missing_software_pi_is_a_warning() -> None:
    pkg = _good_package()
    name, good = _xbrl_text(pkg.content)
    start = good.index("<?instance-generator")
    end = good.index("?>", start) + 2
    broken = _rezip(name, good[:start] + good[end:])
    assert "XML_SOFTWARE_INFO" not in _errors(broken, pkg.filename)
    assert "XML_SOFTWARE_INFO" in _warnings(broken, pkg.filename)


def test_missing_positive_filing_indicator() -> None:
    pkg = _good_package()
    # Assert a template reported that the instance does not positively declare.
    fis = _FIS + [FilingIndicatorSpec(template_code="C_99.00.a", reported=True)]
    assert "MISSING_FILING_INDICATOR" in _errors(pkg.content, pkg.filename, fis)


def test_real_eba_sample_passes_clean() -> None:
    """The check-set accepts a real EBA-produced xBRL-XML instance."""
    from pathlib import Path

    sample = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "sample_xbrl_xml_instance.xbrl"
    )
    name = (
        "DUMMYLEI123456789012.CON_GB_COREP030300_IRRBBDIS"
        "_2025-06-30_20250101000000000.xbrl"
    )
    filename = name[:-5] + ".zip"
    pkg = _rezip(name, sample.read_text())
    # The sample declares filing indicators inline; we assert none extra. Only
    # errors are checked — the sample legitimately warns (unused unit, no PI).
    errors = _errors(pkg, filename, fis=[])
    assert errors == [], errors


def test_unparseable_and_layout() -> None:
    pkg = _good_package()
    name, _ = _xbrl_text(pkg.content)
    assert "XML_UNPARSEABLE" in _errors(
        _rezip(name, "<xbrli:xbrl><oops"), pkg.filename
    )
    # A zip with no .xbrl member.
    empty = io.BytesIO()
    with zipfile.ZipFile(empty, "w") as zf:
        zf.writestr("readme.txt", "nope")
    assert "XML_INSTANCE_LAYOUT" in _errors(empty.getvalue(), pkg.filename)
