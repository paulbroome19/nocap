"""Renders the downloadable validation report (self-contained HTML).

Mirrors the in-UI rule register: run identity, a per-section verdict, then the
register split into three sections **by rule family** (never by severity):

1. **Formula validations** — the evaluated workbook rules (v*/e* codes).
2. **Filing & structural checks** — the EBA Filing Rules + internal NC-S register.
3. **Informational** — notes and deactivated rules.

Every row carries a severity badge (workbook severity for formula rules,
blocking/non-blocking for structural). Explicit formula counts (loaded /
evaluated / satisfied / unsatisfied) appear in the formula section, which is
never rendered green when zero rules evaluated. Deterministic — no wall-clock —
so a run's report is byte-stable.
"""

from __future__ import annotations

from collections.abc import Sequence
from html import escape

from app.validation.register import RegisterRow

_RESULT_CLASS = {
    "PASSED": "pass",
    "FAILED": "fail",
    "WARNING": "warn",
    "NOTE": "note",
    "DEACTIVATED": "note",
}


def _partition(
    register: Sequence[RegisterRow],
) -> tuple[list[RegisterRow], list[RegisterRow], list[RegisterRow]]:
    """Split the register into (formula, structural, informational) by family.

    Informational = NOTE/DEACTIVATED rows (of either source); the rest split on
    source. Severity is never used to place a row.
    """
    formula: list[RegisterRow] = []
    structural: list[RegisterRow] = []
    informational: list[RegisterRow] = []
    for r in register:
        if r.result in ("NOTE", "DEACTIVATED"):
            informational.append(r)
        elif r.source == "formula":
            formula.append(r)
        else:
            structural.append(r)
    return formula, structural, informational


def _sorted(rows: list[RegisterRow]) -> list[RegisterRow]:
    """Failed first, then warnings, then passed; stable within each."""
    order = {"FAILED": 0, "WARNING": 1, "PASSED": 2, "NOTE": 3, "DEACTIVATED": 4}
    return sorted(rows, key=lambda r: order.get(r.result, 5))


def _counts_line(label: str, rows: Sequence[RegisterRow]) -> str:
    total = len(rows)
    passed = sum(1 for r in rows if r.result == "PASSED")
    failed = sum(1 for r in rows if r.result == "FAILED")
    warned = sum(1 for r in rows if r.result == "WARNING")
    parts = [f"{passed}/{total} passed"]
    if failed:
        parts.append(f"{failed} failed")
    if warned:
        parts.append(f"{warned} warning{'s' if warned != 1 else ''}")
    return f"{label}: " + " · ".join(parts)


# Severity badge: workbook severity for formula rules, blocking/non-blocking for
# structural. Red is reserved for the blocking (error) severity.
_BADGE = {
    "error": ("Blocking", "sev-block"),
    "warning": ("Non-blocking", "sev-warn"),
    "info": ("Info", "sev-info"),
}


def _severity_badge(r: RegisterRow) -> str:
    label_cls = _BADGE.get(r.severity or "")
    if label_cls is None:
        # A passed/deactivated row with no failure severity, or a formula rule
        # with no workbook severity — shown, but never as a failure colour.
        label, cls = ("Unknown", "sev-info") if r.source == "formula" else ("—", "sev-none")
    else:
        label, cls = label_cls
    return f'<span class="badge {cls}">{escape(label)}</span>'


def _evaluations_html(r: RegisterRow) -> str:
    """Per-evaluation detail for a formula row: the compared values + cells."""
    evals = r.evaluations or []
    if not evals:
        return ""
    items = []
    for e in evals:
        cell = ""
        if e.get("template_code"):
            cell = escape(
                f"{e['template_code']} r{e.get('row_code','')} c{e.get('column_code','')}"
            )
        values = escape(str(e.get("values") or e.get("message") or ""))
        items.append(
            f"<li><span class=mono>{cell or '—'}</span> "
            f"<span class=mono>{values}</span></li>"
        )
    return "<ul class=evals>" + "".join(items) + "</ul>"


def _rows_html(rows: Sequence[RegisterRow]) -> str:
    out = []
    for r in _sorted(list(rows)):
        cls = _RESULT_CLASS.get(r.result, "note")
        # Formula rows lead their detail with the rule expression (rule_text);
        # structural rows with the plain-English provenance (description).
        provenance = r.rule_text if r.source == "formula" else r.description
        counts = ""
        if r.source == "formula" and (r.satisfied is not None or r.not_satisfied is not None):
            counts = (
                f'<div class="muted">{r.satisfied or 0} satisfied · '
                f"{r.not_satisfied or 0} not satisfied</div>"
            )
        detail_bits = "".join(
            [
                f"<div>{escape(r.detail)}</div>" if r.detail else "",
                f'<div class="muted">{escape(provenance)}</div>' if provenance else "",
                counts,
                _evaluations_html(r),
            ]
        )
        out.append(
            "<tr>"
            f"<td class=mono>{escape(r.id)}</td>"
            f"<td>{escape(r.rule)}</td>"
            f"<td>{_severity_badge(r)}</td>"
            f"<td class=mono>{escape(r.data_evaluated)}</td>"
            f'<td class="result {cls}">{escape(r.result)}</td>'
            f"<td>{detail_bits}</td>"
            "</tr>"
        )
    return "\n".join(out)


def _section(title: str, label: str, rows: Sequence[RegisterRow], *, empty: str) -> str:
    heading = escape(_counts_line(label, rows)) if rows else escape(title)
    if not rows:
        return f"<h2>{escape(title)}</h2>\n<p class=muted>{escape(empty)}</p>"
    return (
        f"<h2>{heading}</h2>\n"
        "<table class=grid><thead><tr>"
        "<th>ID</th><th>Rule</th><th>Severity</th><th>Data evaluated</th>"
        "<th>Result</th><th>Detail</th></tr></thead>\n"
        f"<tbody>{_rows_html(rows)}</tbody></table>"
    )


def _formula_counts_line(formula: dict | None) -> str:
    if not formula or formula.get("status") != "executed":
        return ""
    return (
        "<p class=formula-counts><b>Formula run:</b> "
        f"{formula.get('loaded', 0)} rules loaded, "
        f"{formula.get('evaluated', 0)} evaluated "
        f"({formula.get('satisfied', 0)} satisfied, "
        f"{formula.get('unsatisfied', 0)} unsatisfied).</p>"
    )


def _formula_empty_callout(formula: dict | None, has_rows: bool) -> str:
    """When there are no formula rows, say why — never an implied green pass."""
    if has_rows:
        return ""
    if not formula:
        return "<p class=muted>Formula validation has not run for this run.</p>"
    status = formula.get("status")
    note = escape(str(formula.get("note") or ""))
    if status == "executed" and (formula.get("evaluated", 0) == 0):
        return (
            '<p class="callout bad">Formula validation completed but evaluated '
            "0 rules — treated as a failure, not a pass.</p>"
        )
    if status == "unavailable":
        return f'<p class="callout">Formula validation did not run — {note}.</p>'
    return "<p class=muted>Formula validation has not run for this run.</p>"


def _deactivated_note(formula: dict | None) -> str:
    deactivated = (formula or {}).get("deactivated") or []
    if not deactivated:
        return ""
    return (
        "<p class=muted>Deactivated rules excluded: "
        + ", ".join(f"<span class=mono>{escape(r)}</span>" for r in deactivated)
        + ".</p>"
    )


def build_report_html(
    *,
    identity: Sequence[tuple[str, str]],
    register: Sequence[RegisterRow],
    formula: dict | None,
    scope_statement: str | None = None,
) -> str:
    """Assemble the full HTML validation report (mirrors the register UI)."""
    formula_rows, structural_rows, info_rows = _partition(register)
    failed = sum(1 for r in register if r.result == "FAILED")
    warned = sum(1 for r in register if r.result == "WARNING")
    submittable = failed == 0
    verdict = "Submittable" if submittable else "Not submittable — validation failed"
    verdict_cls = "ok" if submittable else "bad"
    scope_html = (
        f'\n<p class="scope">{escape(scope_statement)}</p>' if scope_statement else ""
    )

    per_section = " &nbsp;·&nbsp; ".join(
        escape(_counts_line(label, rows))
        for label, rows in (
            ("Formula", formula_rows),
            ("Structural", structural_rows),
            ("Informational", info_rows),
        )
    )
    identity_rows = "\n".join(
        f"<tr><th>{escape(k)}</th><td>{escape(v)}</td></tr>" for k, v in identity
    )

    formula_section = (
        _formula_counts_line(formula)
        + _formula_empty_callout(formula, bool(formula_rows))
        + _section(
            "Formula validations", "Formula", formula_rows,
            empty="No formula rules evaluated for this run.",
        )
        + _deactivated_note(formula)
    )

    return f"""<!doctype html>
<html lang=en>
<head>
<meta charset=utf-8>
<title>Carter Validation Report</title>
<style>
  body {{ font: 14px/1.5 -apple-system, Segoe UI, Roboto, sans-serif;
    color: #111111; max-width: 1000px; margin: 2rem auto; padding: 0 1.5rem; }}
  h1 {{ font-size: 20px; margin: 0 0 .25rem; }}
  h2 {{ font-size: 13px; text-transform: uppercase; letter-spacing: .06em;
    color: #344054; margin: 2rem 0 .75rem; }}
  table {{ border-collapse: collapse; width: 100%; }}
  .kv th {{ text-align: left; color: #667085; font-weight: 500; width: 12rem;
    padding: .2rem .5rem .2rem 0; vertical-align: top; }}
  .kv td {{ padding: .2rem 0; }}
  .grid th, .grid td {{ border-bottom: 1px solid #eef0f3; padding: .45rem .6rem;
    text-align: left; vertical-align: top; }}
  .grid th {{ color: #98a2b3; font-weight: 600; font-size: 11px;
    text-transform: uppercase; letter-spacing: .06em; }}
  .mono {{ font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 12px; }}
  .banner {{ display: inline-block; padding: .35rem .75rem; border-radius: 6px;
    font-weight: 600; border-left: 3px solid #ffcd41; }}
  .banner.ok {{ background: #f6f7f9; color: #111111; }}
  .banner.bad {{ background: #f6f7f9; color: #111111; }}
  .result {{ font-weight: 600; }}
  .result.pass {{ color: #344054; }} .result.warn {{ color: #344054; }}
  .result.fail {{ color: #d71e28; }} .result.note {{ color: #667085; }}
  .badge {{ display: inline-block; font-size: 11px; font-weight: 600;
    padding: .1rem .4rem; border-radius: 4px; }}
  .sev-block {{ color: #d71e28; }} .sev-warn {{ color: #344054; }}
  .sev-info {{ color: #98a2b3; }} .sev-none {{ color: #c0c6d0; }}
  .muted {{ color: #98a2b3; }}
  .evals {{ margin: .35rem 0 0; padding-left: 1rem; }}
  .evals li {{ margin: .1rem 0; }}
  .scope, .formula-counts {{ color: #344054; margin: .35rem 0 0; }}
  .callout {{ padding: .5rem .75rem; border-radius: 6px; background: #f6f7f9;
    border-left: 3px solid #98a2b3; }}
  .callout.bad {{ border-left-color: #d71e28; color: #d71e28; font-weight: 600; }}
</style>
</head>
<body>
<h1>Carter — Validation Report</h1>
<p><span class="banner {verdict_cls}">{escape(verdict)}</span>
  &nbsp; {failed} failed, {warned} warning(s), {len(register)} rules</p>
<p class=muted>{per_section}</p>{scope_html}

<h2>Run identity</h2>
<table class=kv>{identity_rows}</table>

{formula_section}

{_section("Filing & structural checks", "Structural", structural_rows,
          empty="No structural checks ran for this run.")}

{_section("Informational", "Informational", info_rows,
         empty="No informational notes for this run.")}
</body>
</html>
"""
