"""Builder for a tiny fixture DPM SQLite database.

Mimics the subset of the real DPM 2.0 schema the lookup service queries (see
docs/dpm-notes.md), with a handful of fictional rows. **Never** the real EBA
file. Used to test the lookup and ingestion flows without mdbtools/Access.

Shape (fictional values):
  - Releases 1 (old) and 2 (current, IsCurrent=-1).
  - Framework COREP; module COREP_LCR_DA (ModuleVID 10), valid from release 1.
  - Template C_67.00.a (TableVID 100 / TableID 500) + C_72.00.a (101 / 501).
  - Table 500 headers: rows (Y) 0010, 0020; columns (X) 0010, 0060. Column 0060
    is deliberately release-versioned in two windows [1,2) and [2,∞) to exercise
    the exclusive-end predicate (must resolve to exactly one row at release 2).
  - Cells: (row 0020, col 0060) -> monetary datapoint 900;
           (row 0010, col 0010) -> percentage datapoint 901.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE Release (ReleaseID INTEGER PRIMARY KEY, IsCurrent INTEGER NOT NULL, Code TEXT);
CREATE TABLE Framework (FrameworkID INTEGER PRIMARY KEY, Code TEXT, Name TEXT);
CREATE TABLE Module (ModuleID INTEGER PRIMARY KEY, FrameworkID INTEGER);
CREATE TABLE ModuleVersion (ModuleVID INTEGER PRIMARY KEY, ModuleID INTEGER, Code TEXT,
    StartReleaseID INTEGER, EndReleaseID INTEGER, VersionNumber TEXT, Name TEXT,
    FromReferenceDate TEXT, ToReferenceDate TEXT);
CREATE TABLE ModuleVersionComposition (ModuleVID INTEGER, TableID INTEGER, TableVID INTEGER);
CREATE TABLE TableVersion (TableVID INTEGER PRIMARY KEY, TableID INTEGER, Code TEXT, Name TEXT,
    StartReleaseID INTEGER, EndReleaseID INTEGER, KeyID INTEGER);
CREATE TABLE Header (HeaderID INTEGER PRIMARY KEY, TableID INTEGER, Direction TEXT);
CREATE TABLE HeaderVersion (HeaderVID INTEGER PRIMARY KEY, HeaderID INTEGER, Code TEXT,
    StartReleaseID INTEGER, EndReleaseID INTEGER);
CREATE TABLE Cell (CellID INTEGER PRIMARY KEY, TableID INTEGER, RowID INTEGER,
    ColumnID INTEGER, SheetID INTEGER);
CREATE TABLE TableVersionCell (TableVID INTEGER, CellID INTEGER,
    VariableVID INTEGER, CellCode TEXT);
CREATE TABLE Variable (VariableID INTEGER PRIMARY KEY, Type TEXT);
CREATE TABLE VariableVersion (VariableVID INTEGER PRIMARY KEY, VariableID INTEGER,
    PropertyID INTEGER, ContextID INTEGER, StartReleaseID INTEGER, EndReleaseID INTEGER);
CREATE TABLE Property (PropertyID INTEGER PRIMARY KEY, DataTypeID INTEGER,
    IsMetric INTEGER, PeriodType TEXT);
CREATE TABLE DataType (DataTypeID INTEGER PRIMARY KEY, Code TEXT, Name TEXT);
-- xBRL-XML context assembly (see docs/xml-notes.md): the metric/dimension codes
-- + member QNames (ItemCategory in the _PR category 1002), and the datapoint's
-- dimensional signature (Context.Signature = "{PropertyID}_{ItemID}#…").
CREATE TABLE ItemCategory (ItemID INTEGER, StartReleaseID INTEGER, CategoryID INTEGER,
    EndReleaseID INTEGER, Code TEXT, Signature TEXT);
CREATE TABLE Context (ContextID INTEGER PRIMARY KEY, Signature TEXT);
"""

_ROWS = {
    # Real EBA framework release codes: current is 4.2 (framework version 4.2),
    # so a run's framework version matches the mini validation-rules tokens
    # (COREP_LCR_DA_4.2) and rule scoping is exercised end-to-end.
    "Release": [(1, 0, "4.1"), (2, -1, "4.2")],
    "Framework": [(1, "COREP", "Common Reporting")],
    "Module": [(1, 1)],
    "ModuleVersion": [
        (10, 1, "COREP_LCR_DA", 1, None, "3.3.0", "LCR Delegated Act - COREP",
         "2024-12-31", None),
    ],
    "ModuleVersionComposition": [(10, 500, 100), (10, 501, 101), (10, 502, 102)],
    "TableVersion": [
        # KeyID NULL => closed table; set => open/keyed (v1-unsupported).
        (100, 500, "C_67.00.a", "Concentration of funding", 1, None, None),
        (101, 501, "C_72.00.a", "Liquidity Coverage. Liquid assets", 1, None, None),
        (102, 502, "C_77.00", "Perimeter of consolidation", 1, None, 999),
    ],
    "Header": [
        (1, 500, "Y"),  # row 0010
        (2, 500, "Y"),  # row 0020
        (3, 500, "X"),  # col 0010
        (4, 500, "X"),  # col 0060 (versioned)
    ],
    "HeaderVersion": [
        (1, 1, "0010", 1, None),
        (2, 2, "0020", 1, None),
        (3, 3, "0010", 1, None),
        # Column 0060 in two release windows -> exercises exclusive-end dedup.
        (4, 4, "0060", 1, 2),
        (5, 4, "0060", 2, None),
    ],
    "Cell": [
        (1000, 500, 2, 4, None),  # row 0020 x col 0060
        (1001, 500, 1, 3, None),  # row 0010 x col 0010
    ],
    "TableVersionCell": [
        (100, 1000, 900, "{C_67.00.a, r0020, c0060, s0010}"),
        (100, 1001, 901, "{C_67.00.a, r0010, c0010, s0010}"),
    ],
    "Variable": [(900, "fact"), (901, "fact"), (902, "filingindicator")],
    # (VariableVID, VariableID, PropertyID, ...) — VariableID is the xBRL
    # property-group key emitted as dp{id}; kept distinct from VariableVID so the
    # lookup test verifies the correct one is used.
    # (VariableVID, VariableID, PropertyID, ContextID, Start, End). PropertyID is
    # the metric; ContextID is the datapoint's dimensional context.
    "VariableVersion": [
        (900, 9900, 800, 700, 1, None),  # monetary metric mi900, context 700
        (901, 9901, 801, 701, 1, None),  # percentage metric mi901, context 701
    ],
    "Property": [
        (800, 9, 1, "Stock"),  # monetary metric
        (801, 10, 1, "Instant"),  # percentage metric
    ],
    "DataType": [
        (1, "i", "integer"),
        (2, "r", "decimal"),
        (9, "m", "monetary"),
        (10, "p", "percentage"),
    ],
    # _PR category (1002) items: metrics + dimensions. Dimension DA is introduced
    # in release 1 (→ eba_dim_1.0), MC in release 2 (→ eba_dim_2.0); members are
    # ordinary domain items whose Signature is the ready XBRL member QName.
    "ItemCategory": [
        (800, 1, 1002, None, "mi900", "mi900"),   # metric of datapoint 900
        (801, 1, 1002, None, "mi901", "mi901"),   # metric of datapoint 901
        (810, 1, 1002, None, "DA", "eba:DA"),     # dimension DA (rel 1 → 1.0)
        (811, 2, 1002, None, "MC", "eba:MC"),     # dimension MC (rel 2 → 2.0)
        (820, 1, 110, None, "x1", "eba_BA:x1"),   # member in domain BA
        (821, 1, 120, None, "x5", "eba_MC:x5"),   # member in domain MC
    ],
    # Context.Signature = "{dimPropertyID}_{memberItemID}#…".
    "Context": [
        (700, "810_820#811_821#"),  # datapoint 900: DA=eba_BA:x1, MC=eba_MC:x5
        (701, "810_820#"),          # datapoint 901: DA=eba_BA:x1
    ],
}


def build(path: str | Path) -> Path:
    """Create the fixture DPM SQLite database at ``path`` and return it."""
    path = Path(path)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_SCHEMA)
        for table, rows in _ROWS.items():
            placeholders = ",".join("?" * len(rows[0]))
            conn.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)
        conn.commit()
    finally:
        conn.close()
    return path
