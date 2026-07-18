"""Helpers for validation tests (not collected as tests)."""

from __future__ import annotations

import io
import zipfile
from collections import namedtuple

_Res = namedtuple("_Res", ["datapoint_id", "datatype_code"])
_Fact = namedtuple(
    "_Fact",
    ["template_code", "row_code", "column_code", "value", "source_sheet", "source_row"],
)
_Ind = namedtuple("_Ind", ["template_code", "reported"])


def fact(template, row, column, value, *, sheet="facts", src_row=2):
    return _Fact(template, row, column, str(value), sheet, src_row)


def indicator(template, reported=True):
    return _Ind(template, reported)


def resolver(mapping: dict[tuple[str, str, str], tuple[int, str]]):
    def _resolve(t, r, c):
        hit = mapping.get((t, r, c))
        return _Res(*hit) if hit is not None else None

    return _resolve


def make_zip(root: str, members: dict[str, bytes]) -> bytes:
    """Build a zip whose entries are {root}/{relpath} from ``members``."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, content in members.items():
            zf.writestr(f"{root}/{rel}", content)
    return buf.getvalue()


REPORT_PACKAGE_JSON = (
    b'{\n  "documentInfo": {\n    "documentType": '
    b'"https://xbrl.org/report-package/2023"\n  }\n}'
)


def clean_members(csv_rows: dict[str, list[list[str]]]) -> dict[str, bytes]:
    """Build a valid member set: reportPackage.json, report.json, and CRLF CSVs."""

    def csv_bytes(rows: list[list[str]]) -> bytes:
        return ("\r\n".join(",".join(r) for r in rows) + "\r\n").encode()

    members = {
        "META-INF/reportPackage.json": REPORT_PACKAGE_JSON,
        "reports/report.json": b'{"documentInfo": {"documentType": '
        b'"https://xbrl.org/2021/xbrl-csv", "extends": ["http://x/y.json"]}}',
    }
    for name, rows in csv_rows.items():
        members[f"reports/{name}"] = csv_bytes(rows)
    return members
