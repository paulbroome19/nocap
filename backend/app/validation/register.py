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


# The structural check registry: every structural check a validation run can
# emit has an entry here — a source reference (published EBA Filing Rule / v5.8
# CSV rule where one exists, else an internal NC-S** id), a short title, and a
# plain-English sentence of what was checked and why. No check renders without
# one (enforced by tests/validation/test_check_registry). Registry order is the
# register's display order for structural rows.
@dataclass(frozen=True)
class StructuralCheck:
    code: str          # the finding code the validation stage emits
    ref: str           # published source reference (FR 1.7.1 / v5.8 CSV-6 / NC-S**)
    title: str         # short statement of the rule
    description: str    # plain-English: what was checked and why
    scope: str         # register grouping label


STRUCTURAL_CHECKS: tuple[StructuralCheck, ...] = (
    StructuralCheck(
        "UNRESOLVED_FACT", "NC-S01",
        "Every (report, row, column) resolves to a datapoint",
        "Each reported cell must map to a real datapoint in the bound taxonomy "
        "release. An unresolved cell means the template/row/column does not "
        "exist for this release and cannot be filed.",
        "Facts",
    ),
    StructuralCheck(
        "DATATYPE_MISMATCH", "NC-S02",
        "Fact value conforms to the datapoint datatype",
        "A monetary datapoint must carry a number, a date a date, and so on. "
        "The submitted value was not valid for its datapoint's datatype.",
        "Facts",
    ),
    StructuralCheck(
        "PERCENTAGE_NOT_RATIO", "FR 3.2(b)",
        "Percentages reported as ratios, not percents",
        "EBA percentage datapoints are filed as decimal ratios (0.15, not 15). "
        "A value above 1 on a percentage datapoint is almost always a percent "
        "entered by mistake.",
        "Percentage facts",
    ),
    StructuralCheck(
        "DUPLICATE_FACT", "NC-S03",
        "Each datapoint is reported at most once",
        "The same (template, row, column) was reported more than once with "
        "conflicting values; a datapoint may appear only once in a submission.",
        "Facts",
    ),
    StructuralCheck(
        "OPEN_TABLE_UNSUPPORTED", "NC-S04",
        "Open/keyed tables are not generated (v1)",
        "A fact targets an open (per-key) table, which this version does not "
        "generate. The fact is excluded rather than written into a malformed CSV.",
        "Open tables",
    ),
    StructuralCheck(
        "MISSING_FILING_INDICATOR", "FR 1.7.1",
        "A template with facts has a positive filing indicator",
        "Every template that carries reported data must declare a positive "
        "filing indicator, so the receiver knows the template was filed.",
        "Templates",
    ),
    StructuralCheck(
        "EMPTY_FILING_INDICATOR", "FR 1.7",
        "A positive filing indicator has facts",
        "A template declared as filed (positive indicator) but carrying no data "
        "is contradictory — either report data or declare it not filed.",
        "Templates",
    ),
    StructuralCheck(
        "INDICATOR_NOT_IN_MODULE", "FR 1.6.3",
        "Filing indicators reference templates in the module",
        "A filing indicator names a template that is not part of this reporting "
        "module; indicators must reference templates the module contains.",
        "Indicators",
    ),
    StructuralCheck(
        "TEMPLATE_DECLARED_NOT_FILED", "NC-S05",
        "Not-required declarations exclude the template's facts",
        "A template was declared not required, so any facts supplied for it were "
        "excluded from the package. Surfaced so the exclusion is never silent.",
        "Templates",
    ),
    StructuralCheck(
        "REQUIRED_TEMPLATE_EMPTY", "NC-S16",
        "Templates declared required are filed",
        "A template was declared required for this entity and workflow, so it "
        "must carry data. A required template with no facts fails the run — "
        "either report its data or change it to optional or not required.",
        "Templates",
    ),
    StructuralCheck(
        "FILENAME_CONVENTION", "NC-S06",
        "Package filename follows the EBA naming convention",
        "The generated report filename must follow the EBA naming convention "
        "(entity, module, reference date) so downstream systems can route it.",
        "Package",
    ),
    StructuralCheck(
        "PACKAGE_UNREADABLE", "NC-S07",
        "Package is a readable report-package zip",
        "The produced package must be a valid, readable zip. An unreadable "
        "archive cannot be submitted or validated further.",
        "Package",
    ),
    StructuralCheck(
        "PACKAGE_LAYOUT", "NC-S08",
        "Report package layout conforms (Report Package 2023)",
        "The package's internal folder layout must conform to the xBRL Report "
        "Package 2023 specification the EBA filing rules require.",
        "Package",
    ),
    StructuralCheck(
        "NOT_CRLF", "NC-S09",
        "CSV files use CRLF line endings",
        "OIM xBRL-CSV requires CRLF line endings; a CSV using bare LF is "
        "non-conformant.",
        "CSV",
    ),
    StructuralCheck(
        "EMPTY_HEADER", "NC-S10",
        "CSV header rows have no empty cells",
        "Every column in a CSV header must be named; an empty header cell makes "
        "the column ambiguous to the receiver.",
        "CSV",
    ),
    StructuralCheck(
        "INCONSISTENT_FIELD_COUNT", "NC-S11",
        "CSV rows have a consistent field count",
        "Every data row must have the same number of fields as the header; a "
        "ragged row indicates a malformed CSV.",
        "CSV",
    ),
    StructuralCheck(
        "FORBIDDEN_SPECIAL_VALUE", "NC-S12",
        "No forbidden OIM special values (#empty, …)",
        "OIM reserves tokens such as #empty; using them as literal cell values "
        "is forbidden by the filing rules.",
        "CSV",
    ),
    StructuralCheck(
        "DECIMALS_SUFFIX", "NC-S13",
        "No decimals suffix in factValue (use parameters.csv)",
        "Decimals are declared once in parameters.csv, not appended to each "
        "fact value; an inline decimals suffix is non-conformant.",
        "CSV",
    ),
    StructuralCheck(
        "KEY_COLUMN_EMPTY", "NC-S14",
        "Key columns populated for reported facts",
        "Every reported fact must populate its table's key columns; an empty "
        "key column leaves the fact uncontextualised.",
        "CSV",
    ),
    StructuralCheck(
        "PARAM_MISSING", "NC-S15",
        "Required parameters present",
        "The package parameters (entity, reference period, currency, decimals) "
        "must all be present and well-formed for the submission to be complete.",
        "Parameters",
    ),
    StructuralCheck(
        "PARAM_WRONGLY_INCLUDED", "v5.8 params",
        "Parameters included only when a fact needs them",
        "A parameter is declared that no reported fact references; the filing "
        "rules require parameters to be present only when a fact uses them.",
        "Parameters",
    ),
    StructuralCheck(
        "ENTRY_POINT_UNVERIFIED", "NC-S17",
        "Entry-point URL verified against the taxonomy",
        "The report's declared taxonomy entry point could not be verified "
        "against the release's taxonomy package (informational without it).",
        "Package",
    ),
    StructuralCheck(
        "VALIDATOR_ERROR", "NC-S18",
        "Validation check ran to completion",
        "A structural validation check raised an unexpected error and could not "
        "complete; its result is unknown and the run is treated as failing.",
        "Package",
    ),
    StructuralCheck(
        "FORMULA_VALIDATION_UNAVAILABLE", "NC-S19",
        "Formula validation available for this release",
        "EBA formula validation could not run — usually because the release has "
        "no taxonomy package — so formula rules were not evaluated.",
        "Formula",
    ),
    # --- xBRL-XML instance checks (docs/xml-notes.md §9) --------------------
    StructuralCheck(
        "XML_INSTANCE_LAYOUT", "NC-S20",
        "Package holds a single xBRL-XML instance",
        "An xBRL-XML package must contain exactly one .xbrl instance document at "
        "the zip root; anything else is not a submittable instance package.",
        "XML instance",
    ),
    StructuralCheck(
        "XML_UNPARSEABLE", "NC-S21",
        "Instance is well-formed XML",
        "The generated .xbrl instance must be well-formed XML; a document that "
        "does not parse cannot be validated or submitted.",
        "XML instance",
    ),
    StructuralCheck(
        "XML_SCHEMAREF", "FR 2.2/2.3",
        "Exactly one absolute .xsd schemaRef",
        "The instance must carry exactly one link:schemaRef pointing at an "
        "absolute .xsd taxonomy entry point, so the receiver binds the right "
        "taxonomy.",
        "XML instance",
    ),
    StructuralCheck(
        "XML_FORBIDDEN_CONSTRUCT", "FR 2.1/2.4/2.14",
        "No xml:base, linkbaseRef, or segment",
        "The filing rules forbid xml:base, link:linkbaseRef, and xbrli:segment "
        "in a filed instance; dimensional context belongs in xbrli:scenario.",
        "XML instance",
    ),
    StructuralCheck(
        "XML_CONTEXT_HYGIENE", "FR 2.7",
        "No unused or duplicated contexts",
        "Every xbrli:context must be referenced by a fact or filing indicator, "
        "and no two contexts may share the same entity, period, and scenario.",
        "XML instance",
    ),
    StructuralCheck(
        "XML_SINGLE_SUBJECT", "FR 2.9",
        "Instance reports a single subject",
        "All contexts must name the same entity identifier; a report covers one "
        "reporting subject, so multiple identifiers indicate a malformed instance.",
        "XML instance",
    ),
    StructuralCheck(
        "XML_PERIOD", "FR 2.10/2.13",
        "Every context has a valid period",
        "Each xbrli:context must carry a period; a context without one leaves its "
        "facts without a reporting reference date.",
        "XML instance",
    ),
    StructuralCheck(
        "XML_DIMENSION_SCENARIO", "FR 2.15",
        "Dimensions appear only in scenario",
        "Explicit dimension members must sit inside xbrli:scenario, never in a "
        "segment, so dimensional qualification is read where the rules require it.",
        "XML instance",
    ),
    StructuralCheck(
        "XML_DUPLICATE_FACT", "FR 2.16",
        "No duplicate facts",
        "The same concept reported against the same context is a duplicate fact; "
        "each datapoint must appear once in the instance.",
        "XML instance",
    ),
    StructuralCheck(
        "XML_DECIMALS", "FR 2.17/2.18",
        "Numeric facts use @decimals, not @precision",
        "Numeric facts must declare accuracy with @decimals and must not use "
        "@precision, which the EBA filing rules prohibit.",
        "XML instance",
    ),
    StructuralCheck(
        "XML_UNIT_HYGIENE", "FR 2.21/2.22",
        "No unused or duplicated units",
        "Every xbrli:unit must be referenced by a fact and each unit id must be "
        "unique; unused or duplicated units are non-conformant.",
        "XML instance",
    ),
    StructuralCheck(
        "XML_SHORT_ID", "FR 2.6",
        "Context and unit ids are short and non-semantic",
        "Context and unit identifiers should be short, whitespace-free, "
        "non-semantic tokens rather than long encoded strings.",
        "XML instance",
    ),
    StructuralCheck(
        "XML_SOFTWARE_INFO", "FR 2.26",
        "Generating-software processing instruction present",
        "The instance must carry a processing instruction identifying the "
        "software that generated it, per the filing rules.",
        "XML instance",
    ),
)

CHECK_BY_CODE: dict[str, StructuralCheck] = {c.code: c for c in STRUCTURAL_CHECKS}


def structural_check(code: str) -> StructuralCheck | None:
    """The registry entry for a structural finding code, if catalogued."""
    return CHECK_BY_CODE.get(code)


_SEVERITY_RESULT = {
    Severity.error: "FAILED",
    Severity.warning: "WARNING",
    Severity.info: "NOTE",
}
_SEVERITY_NAME = {
    Severity.error: "error",
    Severity.warning: "warning",
    Severity.info: "info",
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
    # Plain-English provenance (structural checks) — what was checked and why.
    description: str | None = None
    # Display severity of the row: "error" | "warning" | "info" | None (unknown).
    severity: str | None = None
    # True when a FAILED row blocks submission (error severity).
    blocking: bool = False
    # Per-evaluation detail for formula rows: [{message, values, template_code,
    # row_code, column_code}], the individual failing contexts.
    evaluations: list | None = None
    # Formula evaluation counts, so "N evaluations" is never bare.
    satisfied: int | None = None
    not_satisfied: int | None = None


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
    for check in STRUCTURAL_CHECKS:
        hits = by_code.get(check.code, [])
        if not hits:
            rows.append(
                RegisterRow(
                    id=check.ref, rule=check.title, source="structural",
                    template=None, data_evaluated=check.scope, result="PASSED",
                    detail="", description=check.description,
                )
            )
            continue
        for f in hits:
            rows.append(
                RegisterRow(
                    id=check.ref,
                    rule=check.title,
                    source="structural",
                    template=f.template_code,
                    data_evaluated=_location(f) or check.scope,
                    result=_SEVERITY_RESULT.get(f.severity, "NOTE"),
                    detail=f.message,
                    description=check.description,
                    severity=_SEVERITY_NAME.get(f.severity),
                    blocking=f.severity is Severity.error,
                )
            )
    # Any structural finding outside the registry still surfaces (but the
    # registry-completeness test ensures this stays empty in practice).
    for code, hits in by_code.items():
        if code in CHECK_BY_CODE:
            continue
        for f in hits:
            rows.append(
                RegisterRow(
                    id=code, rule=code, source="structural",
                    template=f.template_code, data_evaluated=_location(f),
                    result=_SEVERITY_RESULT.get(f.severity, "NOTE"),
                    detail=f.message,
                    severity=_SEVERITY_NAME.get(f.severity),
                    blocking=f.severity is Severity.error,
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
        severity = rule.get("severity")
        result = rule.get("result", "PASSED")
        rows.append(
            RegisterRow(
                id=rule["rule_id"],
                rule=rule.get("assertion_type", "Assertion"),
                source="formula",
                template=template,
                data_evaluated=data_eval,
                result=result,
                detail=detail,
                rule_text=descriptions.get(rule["rule_id"]),
                severity=severity,
                blocking=bool(rule.get("blocking")) and result == "FAILED",
                evaluations=rule.get("evaluations") or None,
                satisfied=sat,
                not_satisfied=notsat,
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
