"""The structural-check inventory — the "checks executed" dimension.

Every completed structural validation runs the same catalogue of check
categories; whether each *passed* is derived from the findings it produced. This
turns the flat findings list into an auditable "these checks ran, here is the
result of each" report, alongside the formula-validation summary.

Pure functions over generic ``Finding`` objects — imports only ``core``/its own
stage. Formula rules live in ``arelle_adapter`` (the deactivated list is echoed
here for the report note).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.validation.arelle_adapter import DEACTIVATED_RULES_DEFAULT
from app.validation.models import Severity
from app.validation.schemas import Finding


@dataclass(frozen=True)
class CheckSpec:
    key: str
    label: str
    codes: tuple[str, ...]


# The structural check categories, in report order. Each groups the finding
# codes the validators can raise for that category (see validation.service).
STRUCTURAL_CHECKS: tuple[CheckSpec, ...] = (
    CheckSpec(
        "datapoint_resolution",
        "Datapoint resolution",
        ("UNRESOLVED_FACT",),
    ),
    CheckSpec(
        "datatype_conformance",
        "Datatype conformance",
        ("DATATYPE_MISMATCH", "PERCENTAGE_NOT_RATIO"),
    ),
    CheckSpec("duplicate_facts", "Duplicate facts", ("DUPLICATE_FACT",)),
    CheckSpec(
        "open_table_support",
        "Open-table support",
        ("OPEN_TABLE_UNSUPPORTED",),
    ),
    CheckSpec(
        "filing_indicators",
        "Filing-indicator consistency",
        (
            "MISSING_FILING_INDICATOR",
            "EMPTY_FILING_INDICATOR",
            "INDICATOR_NOT_IN_MODULE",
            "TEMPLATE_DECLARED_NOT_FILED",
        ),
    ),
    CheckSpec(
        "package_filename",
        "Package filename convention",
        ("FILENAME_CONVENTION",),
    ),
    CheckSpec(
        "package_layout",
        "Package layout",
        ("PACKAGE_LAYOUT", "PACKAGE_UNREADABLE"),
    ),
    CheckSpec(
        "csv_wellformedness",
        "CSV well-formedness",
        (
            "NOT_CRLF",
            "EMPTY_HEADER",
            "INCONSISTENT_FIELD_COUNT",
            "FORBIDDEN_SPECIAL_VALUE",
            "DECIMALS_SUFFIX",
            "KEY_COLUMN_EMPTY",
        ),
    ),
    CheckSpec(
        "parameters",
        "Parameters completeness",
        ("PARAM_MISSING", "PARAM_WRONGLY_INCLUDED"),
    ),
    CheckSpec(
        "entry_point",
        "Entry-point verification",
        ("ENTRY_POINT_UNVERIFIED",),
    ),
)

_CODE_TO_CHECK = {code: c.key for c in STRUCTURAL_CHECKS for code in c.codes}
# A catch-all so an uncatalogued structural code still surfaces.
_OTHER = CheckSpec("other", "Other structural checks", ())


@dataclass(frozen=True)
class CheckResult:
    key: str
    label: str
    status: str  # "pass" | "warning" | "fail" | "note"
    errors: int
    warnings: int
    infos: int


def _status(errors: int, warnings: int, infos: int) -> str:
    if errors:
        return "fail"
    if warnings:
        return "warning"
    if infos:
        return "note"
    return "pass"


def structural_check_results(
    findings: Sequence[Finding],
) -> list[CheckResult]:
    """Result of each structural check category, derived from the findings.

    Includes every catalogued check (so a clean run shows them all passing),
    plus an "Other" row if any structural code fell outside the catalogue.
    """
    # code -> (errors, warnings, infos) for structural (non-formula) findings.
    counts: dict[str, list[int]] = {}
    for f in findings:
        if getattr(f.phase, "value", f.phase) == "formula":
            continue
        idx = {Severity.error: 0, Severity.warning: 1, Severity.info: 2}[f.severity]
        key = _CODE_TO_CHECK.get(f.code, _OTHER.key)
        counts.setdefault(key, [0, 0, 0])[idx] += 1

    results: list[CheckResult] = []
    for spec in (*STRUCTURAL_CHECKS, _OTHER):
        e, w, i = counts.get(spec.key, [0, 0, 0])
        if spec.key == _OTHER.key and e + w + i == 0:
            continue  # only show "Other" when something landed there
        results.append(
            CheckResult(spec.key, spec.label, _status(e, w, i), e, w, i)
        )
    return results


def formula_rule_ids(findings: Sequence[Finding]) -> list[str]:
    """Distinct formula rule ids that were unsatisfied (excludes the
    unavailable/info marker)."""
    ids = []
    for f in findings:
        if getattr(f.phase, "value", f.phase) != "formula":
            continue
        if f.code == "FORMULA_VALIDATION_UNAVAILABLE":
            continue
        if f.code not in ids:
            ids.append(f.code)
    return ids


def deactivated_rules() -> list[str]:
    return sorted(DEACTIVATED_RULES_DEFAULT)
