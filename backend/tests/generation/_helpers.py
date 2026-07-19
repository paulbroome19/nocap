"""Helpers for generation tests (not collected as tests)."""

from __future__ import annotations

import io
import zipfile
from collections import namedtuple
from datetime import date

from app.generation.schemas import FactInput, FilingIndicatorSpec, PackageMetadata

_Res = namedtuple("_Res", ["datapoint_id", "datatype_code"])


def fi(template: str, row: str, column: str, value: str) -> FactInput:
    return FactInput(
        template_code=template, row_code=row, column_code=column, value=value
    )


def resolver(mapping: dict[tuple[str, str, str], tuple[int, str]]):
    """Build a fake TemplateResolver from a {(template,row,col): (id, dtype)} map."""

    def _resolve(template: str, row: str, column: str):
        hit = mapping.get((template, row, column))
        return _Res(*hit) if hit is not None else None

    return _resolve


def metadata(**overrides) -> PackageMetadata:
    base = dict(
        entity_lei="5299001234567890ABCD",
        scope="CON",
        country="DE",
        reference_date=date(2025, 12, 31),
        creation_timestamp="20260101000000000",
        framework_code="COREP",
        module_code="COREP_LCR_DA",
        module_version="3.3.0",
        taxonomy_version="4.2",
        base_currency="EUR",
        decimals=-3,
        filing_indicators=[
            FilingIndicatorSpec(template_code="C_73.00.a", reported=True)
        ],
    )
    base.update(overrides)
    return PackageMetadata(**base)


_QName = namedtuple("_QName", ["prefix", "namespace", "local"])
_Member = namedtuple("_Member", ["dimension", "member"])
_XmlRes = namedtuple("_XmlRes", ["metric", "members", "datatype_code"])

_DICT = "http://www.eba.europa.eu/xbrl/crr/dict"


def met(local: str) -> _QName:
    return _QName("eba_met", f"{_DICT}/met", local)


def dim(ver: str, local: str) -> _QName:
    return _QName(f"eba_dim_{ver}", f"{_DICT}/dim/{ver}", local)


def mem(domain: str, local: str) -> _QName:
    return _QName(f"eba_{domain}", f"{_DICT}/dom/{domain}", local)


def xml_resolver(mapping: dict[tuple[str, str, str], _XmlRes]):
    """Fake XmlResolver from {(template,row,col): _XmlRes}."""

    def _resolve(template: str, row: str, column: str):
        return mapping.get((template, row, column))

    return _resolve


def xml_res(metric: _QName, members: list[_Member], datatype: str) -> _XmlRes:
    return _XmlRes(metric, members, datatype)


def open_zip(content: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(content))


def read_member(content: bytes, suffix: str) -> bytes:
    """Read the single member whose path ends with ``suffix``."""
    zf = open_zip(content)
    name = next(n for n in zf.namelist() if n.endswith(suffix))
    return zf.read(name)
