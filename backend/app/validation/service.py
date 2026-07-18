"""Structural validation (v1) — two phases of generic findings.

Runs against already-resolved facts and the built package; emits ``Finding``
objects (severity, code, message, location). Designed so the v2 Arelle adapter
emits into the same structure.

Per the dependency rules this imports only ``core``. Everything from taxonomy /
facts / generation arrives injected (the resolver, facts, filing indicators, the
package bytes). See docs/package-notes.md and the EBA Filing Rules v5.7.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Protocol

from app.validation.models import Severity, ValidationPhase
from app.validation.schemas import Finding

_PRE = ValidationPhase.pre_generation
_POST = ValidationPhase.post_generation


# --- injected shapes -------------------------------------------------------


class Resolution(Protocol):
    datapoint_id: int
    datatype_code: str


Resolver = Callable[[str, str, str], "Resolution | None"]


class FactLike(Protocol):
    template_code: str
    row_code: str
    column_code: str
    value: str
    source_sheet: str | None
    source_row: int | None


class IndicatorLike(Protocol):
    template_code: str
    reported: bool


# datatype code -> the decimals param it needs in parameters.csv.
_DECIMALS_PARAM = {
    "m": "decimalsMonetary",
    "p": "decimalsPercentage",
    "i": "decimalsInteger",
    "r": "decimalsDecimal",
}
_FILENAME_RE = re.compile(
    r"^[A-Za-z0-9-]+(\.[A-Za-z0-9]+)?_[A-Za-z]{2}_[A-Z0-9]+_[A-Z0-9]+"
    r"_\d{4}-\d{2}-\d{2}_\d{17}\.zip$"
)
_DECIMALS_SUFFIX_RE = re.compile(r"^[+-]?\d+(\.\d+)?d[+-]?\d+$")


# --- datatype conformance --------------------------------------------------


def _value_findings(
    datatype_code: str, value: str
) -> list[tuple[Severity, str, str]]:
    """(severity, code, message) issues for a value under its datatype."""
    out: list[tuple[Severity, str, str]] = []
    if datatype_code in {"m", "r", "p", "i"}:
        try:
            dec = Decimal(value)
        except (InvalidOperation, ValueError):
            return [
                (
                    Severity.error,
                    "DATATYPE_MISMATCH",
                    f"value {value!r} is not a valid number for datatype "
                    f"{datatype_code!r}",
                )
            ]
        if datatype_code == "i" and dec != dec.to_integral_value():
            out.append(
                (
                    Severity.error,
                    "DATATYPE_MISMATCH",
                    f"integer datapoint has a fractional value {value!r}",
                )
            )
        if datatype_code == "p" and abs(dec) > 1:
            out.append(
                (
                    Severity.warning,
                    "PERCENTAGE_NOT_RATIO",
                    f"percentage {value!r} looks like a percent, not a ratio; "
                    "EBA rule 3.2(b) requires ratios (e.g. 9.31% -> 0.0931)",
                )
            )
    elif datatype_code in {"d", "dt"}:
        try:
            date.fromisoformat(value[:10])
        except ValueError:
            out.append(
                (
                    Severity.error,
                    "DATATYPE_MISMATCH",
                    f"value {value!r} is not a valid date",
                )
            )
    return out


# --- phase 1: facts --------------------------------------------------------


def validate_facts(
    *,
    facts: Sequence[FactLike],
    resolve: Resolver,
    module_templates: set[str],
    open_templates: set[str],
    filing_indicators: Iterable[IndicatorLike],
    fact_file_name: str,
    entity_id: str | None,
    ref_period: date | None,
    template_of: Callable[[str], str] = lambda code: code,
) -> list[Finding]:
    """``template_of`` collapses a table code to its filing-indicator template
    code (``C_73.00.a`` → ``C_73.00``); the filing-indicator consistency checks
    run at template level, since indicators are per-template. Facts stay
    per-table for resolution and locations."""
    findings: list[Finding] = []

    def _loc(fact: FactLike) -> dict:
        return {
            "file": fact_file_name,
            "sheet": fact.source_sheet,
            "row": fact.source_row,
            "template_code": fact.template_code,
            "row_code": fact.row_code,
            "column_code": fact.column_code,
        }

    by_datapoint: dict[int, list[FactLike]] = defaultdict(list)
    templates_with_facts: set[str] = set()
    open_flagged: set[str] = set()
    for fact in facts:
        # Open/keyed tables are not supported in v1 — flag once per template and
        # skip (they are also excluded from generation, so no malformed CSV).
        if fact.template_code in open_templates:
            if fact.template_code not in open_flagged:
                open_flagged.add(fact.template_code)
                findings.append(
                    Finding(
                        severity=Severity.error,
                        phase=_PRE,
                        code="OPEN_TABLE_UNSUPPORTED",
                        message=f"open-table template {fact.template_code} not "
                        "supported in v1; scheduled",
                        template_code=fact.template_code,
                    )
                )
            continue
        res = resolve(fact.template_code, fact.row_code, fact.column_code)
        if res is None:
            findings.append(
                Finding(
                    severity=Severity.error,
                    phase=_PRE,
                    code="UNRESOLVED_FACT",
                    message="(report, row, column) does not resolve to a "
                    "datapoint in the bound snapshot + release + module",
                    **_loc(fact),
                )
            )
            continue
        templates_with_facts.add(template_of(fact.template_code))
        by_datapoint[res.datapoint_id].append(fact)
        for severity, code, message in _value_findings(res.datatype_code, fact.value):
            findings.append(
                Finding(
                    severity=severity, phase=_PRE, code=code, message=message,
                    **_loc(fact),
                )
            )

    # Duplicate facts (same datapoint reported more than once).
    for datapoint_id, group in by_datapoint.items():
        if len(group) > 1:
            for dup in group[1:]:
                findings.append(
                    Finding(
                        severity=Severity.error,
                        phase=_PRE,
                        code="DUPLICATE_FACT",
                        message=f"datapoint dp{datapoint_id} is reported more "
                        "than once in this run",
                        **_loc(dup),
                    )
                )

    # Filing indicators vs facts, both directions.
    indicators = list(filing_indicators)
    positive = {i.template_code for i in indicators if i.reported}
    for template in sorted(templates_with_facts - positive):
        findings.append(
            Finding(
                severity=Severity.error,
                phase=_PRE,
                code="MISSING_FILING_INDICATOR",
                message="template has reported facts but no positive filing "
                "indicator (rule 1.7.1)",
                template_code=template,
            )
        )
    for template in sorted(positive - templates_with_facts):
        findings.append(
            Finding(
                severity=Severity.warning,
                phase=_PRE,
                code="EMPTY_FILING_INDICATOR",
                message="template is flagged as reported but has no facts "
                "(rule 1.7)",
                template_code=template,
            )
        )
    module_template_ids = {template_of(t) for t in module_templates}
    for template in sorted(
        {i.template_code for i in indicators} - module_template_ids
    ):
        findings.append(
            Finding(
                severity=Severity.error,
                phase=_PRE,
                code="INDICATOR_NOT_IN_MODULE",
                message="filing indicator references a template that is not in "
                "this module (rule 1.6.3)",
                template_code=template,
            )
        )

    # Parameter presence (entityID, refPeriod).
    if not entity_id:
        findings.append(
            Finding(severity=Severity.error, phase=_PRE, code="PARAM_MISSING",
                    message="entityID is missing")
        )
    if ref_period is None:
        findings.append(
            Finding(severity=Severity.error, phase=_PRE, code="PARAM_MISSING",
                    message="refPeriod is missing")
        )

    return findings


# --- phase 2: package ------------------------------------------------------


def _decode_csv(raw: bytes) -> tuple[list[list[str]], bool]:
    """Return (rows, crlf_ok). crlf_ok is False if any newline lacks a CR."""
    text = raw.decode("utf-8")
    crlf_ok = "\r\n" in text and not re.search(r"(?<!\r)\n", text)
    rows = list(csv.reader(io.StringIO(text)))
    return rows, crlf_ok


def validate_package(
    *,
    package_bytes: bytes,
    package_filename: str,
    datatypes_present: set[str],
) -> list[Finding]:
    findings: list[Finding] = []

    if not _FILENAME_RE.match(package_filename):
        findings.append(
            Finding(severity=Severity.error, phase=_POST, code="FILENAME_CONVENTION",
                    message=f"package filename {package_filename!r} does not match "
                    "the EBA naming convention", file=package_filename)
        )

    try:
        zf = zipfile.ZipFile(io.BytesIO(package_bytes))
    except zipfile.BadZipFile as exc:
        findings.append(
            Finding(severity=Severity.error, phase=_POST, code="PACKAGE_UNREADABLE",
                    message=f"package is not a readable zip: {exc}",
                    file=package_filename)
        )
        return findings

    names = zf.namelist()
    root = package_filename[:-4] if package_filename.endswith(".zip") else ""
    roots = {n.split("/")[0] for n in names}
    if roots != {root}:
        findings.append(
            Finding(severity=Severity.error, phase=_POST, code="PACKAGE_LAYOUT",
                    message=f"root folder(s) {sorted(roots)} must be the single "
                    f"folder {root!r} (== zip name)", file=package_filename)
        )
    required = {
        "META-INF/reportPackage.json",
        "reports/report.json",
        "reports/parameters.csv",
        "reports/FilingIndicators.csv",
    }
    present = {n[len(root) + 1 :] for n in names if n.startswith(root + "/")}
    for member in sorted(required - present):
        findings.append(
            Finding(severity=Severity.error, phase=_POST, code="PACKAGE_LAYOUT",
                    message=f"missing required package member {member!r}",
                    file=package_filename)
        )

    findings += _check_report_package_json(zf, root, present)
    findings += _check_csvs(zf, root, present)
    findings += _check_parameters(zf, root, present, datatypes_present)

    # Entry point is derived by pattern, not verified against the published 4.2
    # COREP taxonomy (which wasn't in the provided package). Informational.
    findings.append(
        Finding(severity=Severity.info, phase=_POST, code="ENTRY_POINT_UNVERIFIED",
                message="report.json entry-point URL is derived by the EBA pattern "
                "and not verified against the published 4.2 COREP taxonomy",
                file="reports/report.json")
    )
    return findings


def _check_report_package_json(
    zf: zipfile.ZipFile, root: str, present: set[str]
) -> list[Finding]:
    member = "META-INF/reportPackage.json"
    if member not in present:
        return []
    try:
        data = json.loads(zf.read(f"{root}/{member}"))
        doc_type = data["documentInfo"]["documentType"]
    except (KeyError, ValueError):
        doc_type = None
    if doc_type != "https://xbrl.org/report-package/2023":
        return [
            Finding(severity=Severity.error, phase=_POST, code="PACKAGE_LAYOUT",
                    message="reportPackage.json documentType is not the Report "
                    "Package 2023 type", file=member)
        ]
    return []


def _check_csvs(
    zf: zipfile.ZipFile, root: str, present: set[str]
) -> list[Finding]:
    findings: list[Finding] = []
    members = sorted(
        p for p in present if p.startswith("reports/") and p.endswith(".csv")
    )
    for member in members:
        name = member.split("/")[-1]
        rows, crlf_ok = _decode_csv(zf.read(f"{root}/{member}"))
        if not crlf_ok:
            findings.append(
                Finding(severity=Severity.error, phase=_POST, code="NOT_CRLF",
                        message="CSV must use CRLF line endings", file=name)
            )
        if not rows:
            continue
        header = rows[0]
        if any(cell.strip() == "" for cell in header):
            findings.append(
                Finding(severity=Severity.error, phase=_POST, code="EMPTY_HEADER",
                        message="header row has an empty cell", file=name, row=1)
            )
        width = len(header)
        key_cols = list(range(2, width))  # columns beyond datapoint,factValue
        for i, row in enumerate(rows[1:], start=2):
            if len(row) != width:
                findings.append(
                    Finding(severity=Severity.error, phase=_POST,
                            code="INCONSISTENT_FIELD_COUNT",
                            message=f"row has {len(row)} fields, expected {width}",
                            file=name, row=i)
                )
                continue
            if any(cell.startswith("#") for cell in row):
                findings.append(
                    Finding(severity=Severity.error, phase=_POST,
                            code="FORBIDDEN_SPECIAL_VALUE",
                            message="forbidden special value "
                            "(#empty/#nil/#none/#...)", file=name, row=i)
                )
            if width >= 2 and _DECIMALS_SUFFIX_RE.match(row[1]):
                findings.append(
                    Finding(severity=Severity.error, phase=_POST,
                            code="DECIMALS_SUFFIX",
                            message=f"decimals-suffix {row[1]!r} not allowed; use "
                            "parameters.csv", file=name, row=i)
                )
            for col in key_cols:
                if row[col].strip() == "":
                    findings.append(
                        Finding(severity=Severity.error, phase=_POST,
                                code="KEY_COLUMN_EMPTY",
                                message=f"key column {header[col]!r} is empty for a "
                                "reported fact", file=name, row=i)
                    )
    return findings


def _check_parameters(
    zf: zipfile.ZipFile,
    root: str,
    present: set[str],
    datatypes_present: set[str],
) -> list[Finding]:
    member = "reports/parameters.csv"
    if member not in present:
        return []
    findings: list[Finding] = []
    rows, _ = _decode_csv(zf.read(f"{root}/{member}"))
    params = {r[0]: r[1] for r in rows[1:] if len(r) >= 2}

    for required in ("entityID", "refPeriod"):
        if required not in params:
            findings.append(
                Finding(severity=Severity.error, phase=_POST, code="PARAM_MISSING",
                        message=f"parameters.csv is missing {required}",
                        file="parameters.csv")
            )

    # baseCurrency / decimals* must be present iff a fact needs them (v5.7).
    checks = [("baseCurrency", "m")] + [
        (param, dtype) for dtype, param in _DECIMALS_PARAM.items()
    ]
    for param, dtype in checks:
        included = param in params
        needed = dtype in datatypes_present
        if included and not needed:
            findings.append(
                Finding(severity=Severity.error, phase=_POST,
                        code="PARAM_WRONGLY_INCLUDED",
                        message=f"{param} is included but no {dtype!r}-typed fact "
                        "is present (must be omitted per v5.7)",
                        file="parameters.csv")
            )
        elif needed and not included:
            findings.append(
                Finding(severity=Severity.error, phase=_POST, code="PARAM_MISSING",
                        message=f"{param} is required (a {dtype!r}-typed fact is "
                        "present) but absent", file="parameters.csv")
            )
    return findings


# --- report artifact -------------------------------------------------------


def build_report_text(
    *, header_lines: list[str], findings: Sequence[Finding]
) -> str:
    """Render a plain-text validation report, readable enough to email."""
    errors = [f for f in findings if f.severity is Severity.error]
    warnings = [f for f in findings if f.severity is Severity.warning]
    infos = [f for f in findings if f.severity is Severity.info]

    lines = ["NoCap — Validation Report", "=" * 60, *header_lines, ""]
    verdict = "FAILED VALIDATION — NOT SUBMITTABLE" if errors else "OK"
    lines.append(
        f"Result: {verdict}  "
        f"({len(errors)} error(s), {len(warnings)} warning(s), {len(infos)} info)"
    )
    for title, group in (
        ("ERRORS", errors),
        ("WARNINGS", warnings),
        ("INFO", infos),
    ):
        if not group:
            continue
        lines += ["", title, "-" * len(title)]
        for f in group:
            lines.append(f"  [{f.code}] {_location(f)}")
            lines.append(f"      {f.message}")
    lines.append("")
    return "\n".join(lines)


def _location(f: Finding) -> str:
    parts: list[str] = []
    if f.file:
        loc = f.file
        if f.sheet:
            loc += f" sheet {f.sheet!r}"
        if f.row is not None:
            loc += f" row {f.row}"
        parts.append(loc)
    cell = " ".join(
        p
        for p in (
            f.template_code,
            f"r{f.row_code}" if f.row_code else None,
            f"c{f.column_code}" if f.column_code else None,
        )
        if p
    )
    if cell:
        parts.append(cell)
    return " · ".join(parts) if parts else "(no location)"
