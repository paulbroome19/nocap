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
    StartReleaseID INTEGER, EndReleaseID INTEGER, VersionNumber TEXT, Name TEXT);
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
    PropertyID INTEGER, StartReleaseID INTEGER, EndReleaseID INTEGER);
CREATE TABLE Property (PropertyID INTEGER PRIMARY KEY, DataTypeID INTEGER,
    IsMetric INTEGER, PeriodType TEXT);
CREATE TABLE DataType (DataTypeID INTEGER PRIMARY KEY, Code TEXT, Name TEXT);
"""

_ROWS = {
    "Release": [(1, 0, "1.0"), (2, -1, "2.0")],
    "Framework": [(1, "COREP", "Common Reporting")],
    "Module": [(1, 1)],
    "ModuleVersion": [
        (10, 1, "COREP_LCR_DA", 1, None, "3.3.0", "LCR Delegated Act - COREP"),
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
    "Variable": [(9900, "fact"), (9901, "fact"), (902, "filingindicator")],
    # (VariableVID, VariableID, ...) — VariableID is the xBRL datapoint id and is
    # deliberately distinct from VariableVID so resolution returns the right one.
    "VariableVersion": [
        (900, 9900, 800, 1, None),
        (901, 9901, 801, 1, None),
    ],
    "Property": [
        (800, 9, 1, "Stock"),  # monetary
        (801, 10, 1, "Instant"),  # percentage
    ],
    "DataType": [
        (1, "i", "integer"),
        (2, "r", "decimal"),
        (9, "m", "monetary"),
        (10, "p", "percentage"),
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
