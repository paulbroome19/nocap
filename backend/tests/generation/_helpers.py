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


def open_zip(content: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(content))


def read_member(content: bytes, suffix: str) -> bytes:
    """Read the single member whose path ends with ``suffix``."""
    zf = open_zip(content)
    name = next(n for n in zf.namelist() if n.endswith(suffix))
    return zf.read(name)
