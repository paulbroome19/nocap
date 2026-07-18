"""A tiny EBA-validation-rules workbook fixture.

A dozen representative rows exercising the shapes the ingestion + register join
care about: an LCR active rule, an Inactive rule, a windowed rule whose
[from, to] excludes an earlier date, a code with two windowed rows (so effective
selection by reporting date matters), a future-dated rule, and an existence rule.
Uses the real 15-column header — including the published "Precondtion"
misspelling and the extra trailing columns — to prove tolerant header handling.
"""

from __future__ import annotations

import io
from datetime import date

# Reporting dates the tests bind to.
D_CURRENT = date(2026, 3, 31)  # covers the 4.2 windows
D_EARLIER = date(2025, 6, 30)  # covers the 4.0 window, before the 4.2 windows

# Real header, with the misspelling and trailing columns.
HEADER = (
    "VR Code", "Source", "Frameworks", "Modules", "Cross module", "Tables",
    "Expression", "Precondtion", "Description", "IsActive",
    "FromReferenceDate", "ToReferenceDate", "Severity", "FromSubmissionDate",
    "Implemented in XBRL",
)

# (vr_code, modules, description, is_active, from, to)
_ROWS = [
    ("v10000_m", "COREP_LCR_DA_4.2", "{C 72.00.a, r0010} >= 0",
     "Active", date(2026, 3, 31), "NULL"),
    ("v10001_m", "COREP_LCR_DA_4.2", "windowed active LCR rule",
     "Active", date(2025, 12, 31), date(2026, 12, 30)),
    ("e10002_e", "COREP_LCR_DA_4.2", "C 00.01 must be filled in",
     "Active", date(2026, 3, 31), "NULL"),
    ("v20000_m", "COREP_LCR_DA_4.2", "deactivated (inactive) LCR rule",
     "Inactive", date(2026, 3, 31), "NULL"),
    # Same code, two windows — effective row depends on the reporting date.
    ("v30000_m", "COREP_OF_4.0", "v30000 old (4.0)",
     "Active", date(2025, 3, 31), date(2026, 3, 30)),
    ("v30000_m", "COREP_OF_4.2", "v30000 new (4.2)",
     "Active", date(2026, 3, 31), date(2027, 12, 30)),
    # Future rule — outside the window at D_CURRENT.
    ("v40000_m", "COREP_LCR_DA_4.2", "future-dated rule",
     "Active", date(2027, 1, 1), "NULL"),
]


def build_bytes() -> bytes:
    """The fixture workbook as .xlsx bytes."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "EBA_VR_mini"
    ws.append(list(HEADER))
    for code, modules, desc, active, frm, to in _ROWS:
        ws.append([
            code, "user_defined", "COREP", modules, "No", "C_72.00.a",
            "with {default: 0}: expr", "{v_C_72.00} ", desc, active,
            frm, to, "warning", frm, "Yes",
        ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
