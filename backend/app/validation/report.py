"""Renders the downloadable validation report (self-contained HTML).

Carries the same substance as the in-UI report: run identity, the checks-executed
inventory (structural check categories with pass/fail + counts, and the formula
rule summary with rule ids and the deactivated-list note), then the findings
detail. Deterministic — no wall-clock, sorted output — so re-deriving a run's
report is byte-stable.
"""

from __future__ import annotations

from collections.abc import Sequence
from html import escape

from app.validation.checks import CheckResult
from app.validation.models import Severity
from app.validation.schemas import Finding
from app.validation.service import _location

_STATUS_LABEL = {
    "pass": "Pass",
    "warning": "Warning",
    "fail": "Fail",
    "note": "Note",
}


def _finding_rows(findings: Sequence[Finding]) -> str:
    rows = []
    for f in findings:
        phase = getattr(f.phase, "value", f.phase)
        phase_label = "formula" if phase == "formula" else "structural"
        rows.append(
            "<tr>"
            f'<td class="sev {f.severity.value}">{escape(f.severity.value)}</td>'
            f"<td>{escape(phase_label)}</td>"
            f"<td class=mono>{escape(f.code)}</td>"
            f"<td class=mono>{escape(_location(f))}</td>"
            f"<td>{escape(f.message)}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _check_rows(checks: Sequence[CheckResult]) -> str:
    rows = []
    for c in checks:
        counts = f"{c.errors}E / {c.warnings}W / {c.infos}I"
        label = _STATUS_LABEL.get(c.status, c.status)
        rows.append(
            "<tr>"
            f"<td>{escape(c.label)}</td>"
            f'<td class="status {c.status}">{label}</td>'
            f"<td class=mono>{counts}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _formula_section(formula: dict | None) -> str:
    if not formula:
        return "<p class=muted>Formula validation has not run for this run.</p>"
    status = formula.get("status")
    deactivated = formula.get("deactivated") or []
    note = formula.get("note")
    if status == "unavailable":
        return (
            "<p><b>Formula validation:</b> not run — "
            f"{escape(str(note or 'unavailable'))}.</p>"
        )
    if status != "executed":
        return "<p class=muted>Formula validation has not run for this run.</p>"

    rule_ids = formula.get("unsatisfied_rule_ids") or []
    parts = [
        "<p><b>Formula validation:</b> executed — "
        f"{len(rule_ids)} rule(s) unsatisfied.</p>"
    ]
    if rule_ids:
        parts.append(
            "<p>Unsatisfied rules: "
            + ", ".join(f"<span class=mono>{escape(r)}</span>" for r in rule_ids)
            + ".</p>"
        )
    if deactivated:
        parts.append(
            "<p class=muted>Deactivated rules excluded (per the EBA "
            "deactivated-rules list): "
            + ", ".join(f"<span class=mono>{escape(r)}</span>" for r in deactivated)
            + ".</p>"
        )
    return "\n".join(parts)


def build_report_html(
    *,
    identity: Sequence[tuple[str, str]],
    structural_checks: Sequence[CheckResult],
    formula: dict | None,
    findings: Sequence[Finding],
) -> str:
    """Assemble the full HTML validation report."""
    errors = [f for f in findings if f.severity is Severity.error]
    warnings = [f for f in findings if f.severity is Severity.warning]
    infos = [f for f in findings if f.severity is Severity.info]
    submittable = not errors
    verdict = "Submittable" if submittable else "Not submittable — validation failed"
    verdict_cls = "ok" if submittable else "bad"

    identity_rows = "\n".join(
        f"<tr><th>{escape(k)}</th><td>{escape(v)}</td></tr>" for k, v in identity
    )

    findings_block = (
        '<table class=grid><thead><tr><th>Severity</th><th>Phase</th>'
        "<th>Code</th><th>Location</th><th>Message</th></tr></thead>"
        f"<tbody>{_finding_rows(findings)}</tbody></table>"
        if findings
        else "<p class=muted>No findings.</p>"
    )

    return f"""<!doctype html>
<html lang=en>
<head>
<meta charset=utf-8>
<title>NoCap Validation Report</title>
<style>
  body {{ font: 14px/1.5 -apple-system, Segoe UI, Roboto, sans-serif;
    color: #0f172a; max-width: 900px; margin: 2rem auto; padding: 0 1.5rem; }}
  h1 {{ font-size: 20px; margin: 0 0 .25rem; }}
  h2 {{ font-size: 14px; text-transform: uppercase; letter-spacing: .05em;
    color: #64748b; margin: 2rem 0 .75rem; }}
  table {{ border-collapse: collapse; width: 100%; }}
  .kv th {{ text-align: left; color: #64748b; font-weight: 500; width: 12rem;
    padding: .2rem .5rem .2rem 0; vertical-align: top; }}
  .kv td {{ padding: .2rem 0; }}
  .grid th, .grid td {{ border-bottom: 1px solid #e2e8f0; padding: .4rem .6rem;
    text-align: left; vertical-align: top; }}
  .grid th {{ color: #64748b; font-weight: 500; font-size: 12px; }}
  .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 12px; }}
  .banner {{ display: inline-block; padding: .35rem .75rem; border-radius: 6px;
    font-weight: 600; }}
  .banner.ok {{ background: #dcfce7; color: #166534; }}
  .banner.bad {{ background: #fee2e2; color: #991b1b; }}
  .status {{ font-weight: 600; }}
  .status.pass {{ color: #166534; }} .status.warning {{ color: #b45309; }}
  .status.fail {{ color: #991b1b; }} .status.note {{ color: #0369a1; }}
  .sev.error {{ color: #991b1b; font-weight: 600; }}
  .sev.warning {{ color: #b45309; font-weight: 600; }}
  .sev.info {{ color: #0369a1; }}
  .muted {{ color: #94a3b8; }}
</style>
</head>
<body>
<h1>NoCap — Validation Report</h1>
<p><span class="banner {verdict_cls}">{escape(verdict)}</span>
  &nbsp; {len(errors)} error(s), {len(warnings)} warning(s), {len(infos)} info</p>

<h2>Run identity</h2>
<table class=kv>{identity_rows}</table>

<h2>Structural checks executed</h2>
<table class=grid><thead><tr><th>Check</th><th>Result</th>
  <th>Findings (E/W/I)</th></tr></thead>
<tbody>{_check_rows(structural_checks)}</tbody></table>

<h2>Formula validation</h2>
{_formula_section(formula)}

<h2>Findings</h2>
{findings_block}
</body>
</html>
"""
