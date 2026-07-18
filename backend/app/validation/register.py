"""The validation rule register — one uniform view over both check sources.

Merges the structural checks and the Arelle formula rules into rows with the
same columns: ID · Rule · Data evaluated · Result · Detail. Every executed rule
appears (PASSED as well as FAILED), so it reads as a bank-grade register rather
than an error list.

Structural rule IDs map to the EBA Filing Rule they implement where one exists
(e.g. FR 1.7.1); internal checks get stable NC-S** ids. Formula rows come from
the per-rule results the adapter captures (satisfied + not-satisfied).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.validation.models import Severity
from app.validation.schemas import Finding

# (code, id, rule, scope) — register order. External FR/v5.8 ids where the rule
# implements a published EBA Filing Rule; NC-S** where it is internal.
STRUCTURAL_RULES: tuple[tuple[str, str, str, str], ...] = (
    ("UNRESOLVED_FACT", "NC-S01",
     "Every (report, row, column) resolves to a datapoint", "Facts"),
    ("DATATYPE_MISMATCH", "NC-S02",
     "Fact value conforms to the datapoint datatype", "Facts"),
    ("PERCENTAGE_NOT_RATIO", "FR 3.2(b)",
     "Percentages reported as ratios, not percents", "Percentage facts"),
    ("DUPLICATE_FACT", "NC-S03",
     "Each datapoint is reported at most once", "Facts"),
    ("OPEN_TABLE_UNSUPPORTED", "NC-S04",
     "Open/keyed tables are not generated (v1)", "Open tables"),
    ("MISSING_FILING_INDICATOR", "FR 1.7.1",
     "A template with facts has a positive filing indicator", "Templates"),
    ("EMPTY_FILING_INDICATOR", "FR 1.7",
     "A positive filing indicator has facts", "Templates"),
    ("INDICATOR_NOT_IN_MODULE", "FR 1.6.3",
     "Filing indicators reference templates in the module", "Indicators"),
    ("TEMPLATE_DECLARED_NOT_FILED", "NC-S05",
     "Not-filed declarations exclude the template's facts", "Templates"),
    ("FILENAME_CONVENTION", "NC-S06",
     "Package filename follows the EBA naming convention", "Package"),
    ("PACKAGE_UNREADABLE", "NC-S07",
     "Package is a readable report-package zip", "Package"),
    ("PACKAGE_LAYOUT", "NC-S08",
     "Report package layout conforms (Report Package 2023)", "Package"),
    ("NOT_CRLF", "NC-S09", "CSV files use CRLF line endings", "CSV"),
    ("EMPTY_HEADER", "NC-S10", "CSV header rows have no empty cells", "CSV"),
    ("INCONSISTENT_FIELD_COUNT", "NC-S11",
     "CSV rows have a consistent field count", "CSV"),
    ("FORBIDDEN_SPECIAL_VALUE", "NC-S12",
     "No forbidden OIM special values (#empty, …)", "CSV"),
    ("DECIMALS_SUFFIX", "NC-S13",
     "No decimals suffix in factValue (use parameters.csv)", "CSV"),
    ("KEY_COLUMN_EMPTY", "NC-S14",
     "Key columns populated for reported facts", "CSV"),
    ("PARAM_MISSING", "NC-S15", "Required parameters present", "Parameters"),
    ("PARAM_WRONGLY_INCLUDED", "v5.8 params",
     "Parameters included only when a fact needs them", "Parameters"),
    ("ENTRY_POINT_UNVERIFIED", "NC-S17",
     "Entry-point URL verified against the taxonomy", "Package"),
)

_SEVERITY_RESULT = {
    Severity.error: "FAILED",
    Severity.warning: "WARNING",
    Severity.info: "NOTE",
}
_CELL_TEMPLATE = re.compile(r"\{([A-Za-z0-9_.]+),")


@dataclass(frozen=True)
class RegisterRow:
    id: str
    rule: str
    source: str  # "structural" | "formula"
    template: str | None  # for the template filter
    data_evaluated: str
    result: str  # PASSED | FAILED | WARNING | NOTE | DEACTIVATED
    detail: str
    # The human-readable rule statement (workbook Description), formula rows only.
    rule_text: str | None = None


def _phase(f: Finding) -> str:
    return getattr(f.phase, "value", f.phase)


def _location(f: Finding) -> str:
    parts: list[str] = []
    if f.template_code:
        cell = f.template_code
        if f.row_code:
            cell += f" r{f.row_code}"
        if f.column_code:
            cell += f" c{f.column_code}"
        parts.append(cell)
    elif f.file:
        loc = f.file
        if f.row is not None:
            loc += f" row {f.row}"
        parts.append(loc)
    return " · ".join(parts)


def _structural_rows(findings: Sequence[Finding]) -> list[RegisterRow]:
    by_code: dict[str, list[Finding]] = {}
    for f in findings:
        if _phase(f) == "formula":
            continue
        by_code.setdefault(f.code, []).append(f)

    rows: list[RegisterRow] = []
    catalogued: set[str] = set()
    for code, rid, rule, scope in STRUCTURAL_RULES:
        catalogued.add(code)
        hits = by_code.get(code, [])
        if not hits:
            rows.append(
                RegisterRow(rid, rule, "structural", None, scope, "PASSED", "")
            )
            continue
        for f in hits:
            rows.append(
                RegisterRow(
                    id=rid,
                    rule=rule,
                    source="structural",
                    template=f.template_code,
                    data_evaluated=_location(f) or scope,
                    result=_SEVERITY_RESULT.get(f.severity, "NOTE"),
                    detail=f.message,
                )
            )
    # Any structural finding outside the catalogue still surfaces.
    for code, hits in by_code.items():
        if code in catalogued:
            continue
        for f in hits:
            rows.append(
                RegisterRow(
                    id=code, rule=code, source="structural",
                    template=f.template_code, data_evaluated=_location(f),
                    result=_SEVERITY_RESULT.get(f.severity, "NOTE"),
                    detail=f.message,
                )
            )
    return rows


def _formula_rows(
    formula: dict | None, descriptions: dict[str, str]
) -> list[RegisterRow]:
    if not formula or formula.get("status") != "executed":
        return []
    rows: list[RegisterRow] = []
    for rule in formula.get("rules", []):
        values = rule.get("values")
        message = rule.get("message")
        sat = rule.get("satisfied", 0)
        notsat = rule.get("not_satisfied", 0)
        template = None
        source_text = values or message or ""
        m = _CELL_TEMPLATE.search(source_text)
        if m:
            template = m.group(1)
        data_eval = values or f"{sat + notsat} evaluation(s)"
        detail = message or f"{sat} satisfied, {notsat} not satisfied"
        rows.append(
            RegisterRow(
                id=rule["rule_id"],
                rule=rule.get("assertion_type", "Assertion"),
                source="formula",
                template=template,
                data_evaluated=data_eval,
                result=rule.get("result", "PASSED"),
                detail=detail,
                rule_text=descriptions.get(rule["rule_id"]),
            )
        )
    return rows


def _deactivated_rows(
    formula: dict | None, inactive: dict[str, str]
) -> list[RegisterRow]:
    """Rules the taxonomy executed but the workbook deactivated for the run.

    Sourced from the (bounded) deactivations the formula run actually traced.
    Flagged rather than dropped silently, so the register stays a complete
    account of what ran.
    """
    if not formula:
        return []
    rows: list[RegisterRow] = []
    for code in formula.get("deactivated", []):
        if code not in inactive:
            continue  # a non-workbook (hardcoded-fallback) deactivation
        rows.append(
            RegisterRow(
                id=code,
                rule="Value Assertion",
                source="formula",
                template=None,
                data_evaluated="—",
                result="DEACTIVATED",
                detail="excluded — workbook marks this rule inactive for the "
                "reporting date",
                rule_text=inactive.get(code) or None,
            )
        )
    return rows


def build_register(
    findings: Sequence[Finding],
    formula: dict | None,
    *,
    rule_meta: dict | None = None,
) -> list[RegisterRow]:
    """The full rule register: structural rows, formula rows, deactivated rows.

    ``rule_meta`` (from the ingested validation-rules workbook, resolved for the
    run's reporting date) carries ``descriptions`` — joined onto formula rows as
    the human rule statement — and ``inactive`` — codes the workbook deactivated,
    surfaced as flagged rows. Absent when no workbook is ingested.
    """
    descriptions = (rule_meta or {}).get("descriptions", {})
    inactive = (rule_meta or {}).get("inactive", {})
    return [
        *_structural_rows(findings),
        *_formula_rows(formula, descriptions),
        *_deactivated_rows(formula, inactive),
    ]
