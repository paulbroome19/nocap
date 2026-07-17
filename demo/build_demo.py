"""Generate the demo input files for a COREP LCR run.

The (template, row, column) combinations below were derived from the real EBA
DPM 2.0 v4.2 release (module COREP_LCR_DA), so the data actually resolves to
datapoints. All entity data is fictional. Re-run to regenerate the XLSX files:

    python demo/build_demo.py

Requires openpyxl (a backend dependency).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from openpyxl import Workbook

HERE = Path(__file__).parent

# Fictional filer.
ENTITY_LEI = "5299001234567890ABCD"  # 20 alphanumeric chars, not a real LEI
REFERENCE_DATE = date(2025, 12, 31)
BASE_CURRENCY = "EUR"
DECIMALS = -3

# Real resolving cells (template, row, column, fictional value). Template codes
# are written in a MIX of the accepted forms on purpose (upstream underscores,
# EBA display space, DB form) to exercise normalisation end-to-end.
FACT_ROWS = [
    # C_73.00.a (Outflows) — upstream underscore form
    ("C_73_00_a", "0010", "0010", 4500000),
    ("C_73_00_a", "0020", "0010", 1250000),
    ("C_73_00_a", "0030", "0010", 830000),
    # C_74.00.a (Inflows) — EBA display (space) form
    ("C 74.00.a", "0010", "0010", 2100000),
    ("C 74.00.a", "0020", "0010", 640000),
    ("C 74.00.a", "0030", "0010", 55000),
    # C_76.00.a (Calculations) — DB form
    ("C_76.00.a", "0010", "0010", 6800000),
    ("C_76.00.a", "0020", "0010", 5400000),
    ("C_76.00.a", "0030", "0010", 1.32),  # a percentage datapoint
]

# Templates reported (filing indicators). DB form; the parser normalises anyway.
FILING_INDICATORS = ["C_72.00.a", "C_73.00.a", "C_74.00.a", "C_76.00.a"]


def build_fact_file(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "facts"
    ws.append(["report", "row", "column", "value"])
    for report, row, col, value in FACT_ROWS:
        ws.append([report, row, col, value])
    wb.save(path)


def build_indicators_params_file(path: Path) -> None:
    wb = Workbook()

    params = wb.active
    params.title = "parameters"
    params.append(["entity_lei", ENTITY_LEI])
    params.append(["reference_date", REFERENCE_DATE])
    params.append(["base_currency", BASE_CURRENCY])
    params.append(["decimals", DECIMALS])

    indicators = wb.create_sheet("filing_indicators")
    indicators.append(["template", "reported"])
    for code in FILING_INDICATORS:
        indicators.append([code, True])

    wb.save(path)


def main() -> None:
    build_fact_file(HERE / "fact_sample.xlsx")
    build_indicators_params_file(HERE / "indicators_params.xlsx")
    print(f"wrote {HERE / 'fact_sample.xlsx'}")
    print(f"wrote {HERE / 'indicators_params.xlsx'}")


if __name__ == "__main__":
    main()
