"""Renders the downloadable validation report (self-contained HTML).

The report mirrors the in-UI rule register exactly: run identity, the merged
register (structural + formula rules with ID · Rule · Source · Data evaluated ·
Result · Detail), and the formula run note (loaded / evaluated / satisfied /
unsatisfied + the deactivated-rules list). Deterministic — no wall-clock — so a
run's report is byte-stable.
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
}


def _register_rows(register: Sequence[RegisterRow]) -> str:
    rows = []
    for r in register:
        cls = _RESULT_CLASS.get(r.result, "note")
        rows.append(
            "<tr>"
            f"<td class=mono>{escape(r.id)}</td>"
            f"<td>{escape(r.rule)}</td>"
            f"<td>{escape(r.source)}</td>"
            f"<td class=mono>{escape(r.data_evaluated)}</td>"
            f'<td class="result {cls}">{escape(r.result)}</td>'
            f"<td>{escape(r.detail)}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _formula_note(formula: dict | None) -> str:
    if not formula:
        return "<p class=muted>Formula validation has not run for this run.</p>"
    if formula.get("status") == "unavailable":
        return (
            "<p><b>Formula validation:</b> not run — "
            f"{escape(str(formula.get('note') or 'unavailable'))}.</p>"
        )
    if formula.get("status") != "executed":
        return "<p class=muted>Formula validation has not run for this run.</p>"
    deactivated = formula.get("deactivated") or []
    parts = [
        "<p><b>Formula validation:</b> executed — "
        f"{formula.get('loaded', 0)} rules loaded, "
        f"{formula.get('evaluated', 0)} evaluated "
        f"({formula.get('satisfied', 0)} satisfied, "
        f"{formula.get('unsatisfied', 0)} unsatisfied).</p>"
    ]
    if deactivated:
        parts.append(
            "<p class=muted>Deactivated rules excluded: "
            + ", ".join(f"<span class=mono>{escape(r)}</span>" for r in deactivated)
            + ".</p>"
        )
    return "\n".join(parts)


def build_report_html(
    *,
    identity: Sequence[tuple[str, str]],
    register: Sequence[RegisterRow],
    formula: dict | None,
) -> str:
    """Assemble the full HTML validation report (mirrors the register UI)."""
    failed = sum(1 for r in register if r.result == "FAILED")
    warned = sum(1 for r in register if r.result == "WARNING")
    submittable = failed == 0
    verdict = "Submittable" if submittable else "Not submittable — validation failed"
    verdict_cls = "ok" if submittable else "bad"

    identity_rows = "\n".join(
        f"<tr><th>{escape(k)}</th><td>{escape(v)}</td></tr>" for k, v in identity
    )

    return f"""<!doctype html>
<html lang=en>
<head>
<meta charset=utf-8>
<title>NoCap Validation Report</title>
<style>
  body {{ font: 14px/1.5 -apple-system, Segoe UI, Roboto, sans-serif;
    color: #0f172a; max-width: 1000px; margin: 2rem auto; padding: 0 1.5rem; }}
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
  .result {{ font-weight: 600; }}
  .result.pass {{ color: #166534; }} .result.warn {{ color: #b45309; }}
  .result.fail {{ color: #991b1b; }} .result.note {{ color: #0369a1; }}
  .muted {{ color: #94a3b8; }}
</style>
</head>
<body>
<h1>NoCap — Validation Report</h1>
<p><span class="banner {verdict_cls}">{escape(verdict)}</span>
  &nbsp; {failed} failed, {warned} warning(s), {len(register)} rules</p>

<h2>Run identity</h2>
<table class=kv>{identity_rows}</table>

<h2>Rule register</h2>
<table class=grid><thead><tr><th>ID</th><th>Rule</th><th>Source</th>
  <th>Data evaluated</th><th>Result</th><th>Detail</th></tr></thead>
<tbody>{_register_rows(register)}</tbody></table>

<h2>Formula validation</h2>
{_formula_note(formula)}
</body>
</html>
"""
