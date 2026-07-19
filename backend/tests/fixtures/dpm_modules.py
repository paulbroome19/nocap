"""Build a minimal DPM SQLite that provides a chosen set of module versions at
its current release — enough for ``TaxonomyLookup.current_modules`` /
``record_release_modules`` and the version-selection dedup tests.

Only the tables ``current_modules`` touches (Release, Framework, Module,
ModuleVersion) are populated; this is not a full DPM (no templates/datapoints).
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
"""


def build_dpm(
    path: Path,
    release_code: str,
    modules: list[tuple[str, str, str, str]],
    *,
    valid_from: str | None = "2026-03-31",
    valid_to: str | None = None,
) -> Path:
    """Write a DPM sqlite whose current release is ``release_code`` and which
    provides ``modules`` = list of (module_code, framework_code, version, name)."""
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_SCHEMA)
        # One current release (ReleaseID 1, IsCurrent=-1 like the Access boolean).
        conn.execute(
            "INSERT INTO Release VALUES (?, ?, ?)", (1, -1, release_code)
        )
        frameworks: dict[str, int] = {}
        for i, (module_code, fw_code, version, name) in enumerate(modules, start=1):
            if fw_code not in frameworks:
                fid = len(frameworks) + 1
                frameworks[fw_code] = fid
                conn.execute(
                    "INSERT INTO Framework VALUES (?, ?, ?)", (fid, fw_code, fw_code)
                )
            fid = frameworks[fw_code]
            conn.execute("INSERT INTO Module VALUES (?, ?)", (i, fid))
            conn.execute(
                "INSERT INTO ModuleVersion VALUES (?,?,?,?,?,?,?,?,?)",
                (i, i, module_code, 1, None, version, name, valid_from, valid_to),
            )
        conn.commit()
    finally:
        conn.close()
    return path
