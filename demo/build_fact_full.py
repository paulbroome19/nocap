"""Generate demo/fact_full.xlsx — the "full run" hero file for the demo.

A fuller COREP LCR fact set engineered so a meaningful number of the module's
formula assertions actually evaluate. It populates every closed cell of the
C_72.00 (Liquid Assets) and C_76.00 (LCR calculation) tables with values
consistent with the rule arithmetic (0 satisfies the sum/inequality rules that
default missing operands to 0), and deliberately mis-sets three cells so a
handful of rules FAIL with real comparison detail.

Focused on C_72/C_76 so the run evaluates in a demo-tolerable window (~2 min of
Arelle) rather than the full module's many minutes.

Requires the real EBA 4.2 DPM ingested as snapshot 1 (backend/data). Re-run:

    python demo/build_fact_full.py

Verified live: 52 assertions evaluated, 46 satisfied, 6 unsatisfied (~115 s).
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from openpyxl import Workbook

HERE = Path(__file__).parent
DPM = HERE.parent / "backend" / "data" / "snapshots" / "1" / "dpm.sqlite"

# C_72 (Liquid Assets) + C_76 (LCR calculation). Closed tables only.
TABLES = ("C_72.00.a", "C_76.00.a", "C_76.00.b")


def _enum_cells() -> list[tuple[str, str, str]]:
    conn = sqlite3.connect(f"file:{DPM}?mode=ro", uri=True)
    rid = conn.execute(
        "SELECT ReleaseID FROM Release WHERE IsCurrent<>0 "
        "ORDER BY ReleaseID DESC LIMIT 1"
    ).fetchone()[0]
    v = (
        "({a}.StartReleaseID<={r} AND "
        "({a}.EndReleaseID IS NULL OR {a}.EndReleaseID>{r}))"
    )
    q = f"""SELECT tv.Code, ry.Code, cx.Code FROM ModuleVersion mv
    JOIN ModuleVersionComposition mvc ON mvc.ModuleVID=mv.ModuleVID
    JOIN TableVersion tv ON tv.TableVID=mvc.TableVID
    JOIN Cell c ON c.TableID=tv.TableID
    JOIN Header hr ON hr.HeaderID=c.RowID AND hr.Direction='Y'
    JOIN Header hc ON hc.HeaderID=c.ColumnID AND hc.Direction='X'
    JOIN HeaderVersion ry ON ry.HeaderID=c.RowID AND {v.format(a='ry', r=rid)}
    JOIN HeaderVersion cx ON cx.HeaderID=c.ColumnID AND {v.format(a='cx', r=rid)}
    JOIN TableVersionCell tvc ON tvc.TableVID=tv.TableVID AND tvc.CellID=c.CellID
    WHERE mv.Code='COREP_LCR_DA' AND tv.KeyID IS NULL
      AND {v.format(a='mv', r=rid)} AND {v.format(a='tv', r=rid)}"""
    return [row for row in conn.execute(q) if row[0] in TABLES]


def main() -> None:
    if not DPM.exists():
        sys.exit(f"DPM not found at {DPM}; ingest the EBA 4.2 release as snapshot 1")

    cells = _enum_cells()
    facts = {(t, r, c): 0 for (t, r, c) in cells}

    # --- three deliberate failures, each with clean comparison detail ---
    c76_c10 = [k for k in facts if k[0] == "C_76.00.a" and k[2] == "0010"]
    if len(c76_c10) >= 2:
        facts[c76_c10[0]] = -450000  # fails "{r,c0010} >= 0"
        facts[c76_c10[1]] = 1750000  # fails "total = sum(components=0)"
    c72_c40 = [k for k in facts if k[0] == "C_72.00.a" and k[2] == "0040"]
    if c72_c40:
        facts[c72_c40[0]] = 980000  # fails a C_72 sum ("0 = 980000 + 0")

    wb = Workbook()
    ws = wb.active
    ws.title = "facts"
    ws.append(["report", "row", "column", "value"])
    for (t, r, c), v in sorted(facts.items()):
        ws.append([t, r, c, v])
    out = HERE / "fact_full.xlsx"
    wb.save(out)
    print(f"wrote {out} ({len(facts)} facts, 3 deliberate failures)")


if __name__ == "__main__":
    main()
