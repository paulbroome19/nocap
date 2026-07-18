"""Permanent guard for the three formula-validation fixes.

This class of bug — a generated package that Arelle silently can't use — has cost
three separate discoveries:

1. dp{VariableVID} instead of dp{VariableID}  → every fact rejected as
   xbrlce:unknownPropertyGroup (facts never load).
2. the taxonomy container passed to Arelle un-expanded → taxonomy never loads
   (formula "unavailable").
3. filing indicators emitted at table level (C_73.00.a) not template level
   (C_73.00) → every assertion precondition fails (Filing Rule 1.6) → nothing
   evaluates.

Each was individually invisible to the unit suite. This end-to-end test pins all
three: it generates a package the app's way and asserts Arelle (a) loads it with
ZERO unknownPropertyGroup errors and (b) evaluates at least one assertion.

It is an *integration* test: it needs Arelle installed and the real EBA 4.2 DPM
+ taxonomy package present under the data dir (they are not in the repo), so it
skips cleanly in a bare checkout and runs in dev / a nightly job.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from app.facts.schemas import FilingIndicator
from app.generation import service as generation
from app.generation.schemas import FactInput, FilingIndicatorSpec, PackageMetadata
from app.taxonomy import service as taxonomy
from app.workflows.service import _template_level_indicators

pytest.importorskip("arelle")

_MODULE = "COREP_LCR_DA"
# C_72 + C_76 — a small, self-contained slice whose single-table LCR assertions
# evaluate quickly (~2 min incl. taxonomy DTS load).
_TABLES = ("C_72.00.a", "C_76.00.a", "C_76.00.b")

# The real data dir (backend/data), independent of the hermetic tests' temp
# DATA_DIR override — this test deliberately uses the real DPM + taxonomy.
_REAL_DATA = Path(__file__).resolve().parents[2] / "data"


def _enum_cells(dpm) -> list[tuple[str, str, str]]:
    conn = sqlite3.connect(f"file:{dpm}?mode=ro", uri=True)
    rid = conn.execute(
        "SELECT ReleaseID FROM Release WHERE IsCurrent<>0 "
        "ORDER BY ReleaseID DESC LIMIT 1"
    ).fetchone()[0]
    valid = (
        "({a}.StartReleaseID<={r} AND "
        "({a}.EndReleaseID IS NULL OR {a}.EndReleaseID>{r}))"
    )
    q = f"""SELECT tv.Code, ry.Code, cx.Code FROM ModuleVersion mv
    JOIN ModuleVersionComposition mvc ON mvc.ModuleVID=mv.ModuleVID
    JOIN TableVersion tv ON tv.TableVID=mvc.TableVID
    JOIN Cell c ON c.TableID=tv.TableID
    JOIN Header hr ON hr.HeaderID=c.RowID AND hr.Direction='Y'
    JOIN Header hc ON hc.HeaderID=c.ColumnID AND hc.Direction='X'
    JOIN HeaderVersion ry ON ry.HeaderID=c.RowID AND {valid.format(a='ry', r=rid)}
    JOIN HeaderVersion cx ON cx.HeaderID=c.ColumnID AND {valid.format(a='cx', r=rid)}
    JOIN TableVersionCell tvc ON tvc.TableVID=tv.TableVID AND tvc.CellID=c.CellID
    WHERE mv.Code='{_MODULE}' AND tv.KeyID IS NULL
      AND {valid.format(a='mv', r=rid)} AND {valid.format(a='tv', r=rid)}"""
    return [row for row in conn.execute(q) if row[0] in _TABLES]


@pytest.mark.integration
def test_generated_package_loads_and_assertions_evaluate() -> None:
    dpm = _REAL_DATA / "snapshots" / "1" / "dpm.sqlite"
    taxo = sorted((_REAL_DATA / "snapshots" / "1" / "taxonomy").glob("*.zip"))
    if not dpm.exists() or not taxo:
        pytest.skip("real EBA 4.2 DPM + taxonomy package not present")
    cache = _REAL_DATA / "cache"

    cells = _enum_cells(dpm)
    assert cells, "expected C_72/C_76 cells in the DPM"
    facts = {(t, r, c): 0 for (t, r, c) in cells}

    with taxonomy.TaxonomyLookup(dpm) as lk:
        rid = lk.default_release_id()
        meta = lk.module_metadata(_MODULE, release_id=rid)

        def resolve(t, r, c):
            return lk.resolve(t, r, c, release_id=rid)

        # Filing indicators through the real collapse path (pins fix #3): if this
        # regresses to table-level codes, preconditions fail and nothing evaluates.
        indicators = _template_level_indicators(
            [FilingIndicator(template_code=t, reported=True) for t in _TABLES]
        )
        md = PackageMetadata(
            entity_lei="213800MERIDNGRPHLD42", scope="CON", country="GB",
            reference_date=date(2025, 12, 31),
            creation_timestamp="20251231000000999",
            framework_code=meta.framework_code, module_code=_MODULE,
            module_version=meta.module_version,
            taxonomy_version=lk.release_code(rid) or "4.2",
            base_currency="EUR", decimals=-3,
            filing_indicators=[
                FilingIndicatorSpec(template_code=i.template_code, reported=i.reported)
                for i in indicators
            ],
        )
        package = generation.build_package(
            [
                FactInput(template_code=t, row_code=r, column_code=c, value=str(v))
                for (t, r, c), v in facts.items()
            ],
            md,
            resolve=resolve,
            strict=False,
        )

    cache.mkdir(parents=True, exist_ok=True)
    out = cache / "guard_pkg.zip"
    out.write_bytes(package.content)

    from app.validation.arelle_adapter import ArelleFormulaValidator

    run = ArelleFormulaValidator(cache_dir=cache).validate_detailed(out, taxo)

    # (a) the package loads — no fact rejected as an unknown property group.
    assert run.available, run.unavailable_reason
    assert run.unknown_property_groups == 0, (
        f"{run.unknown_property_groups} facts rejected as unknownPropertyGroup — "
        "the dp{VariableID} mapping regressed"
    )
    # (b) at least one assertion actually evaluated (bound to facts).
    assert len(run.rule_results) >= 1, (
        "no formula assertion evaluated — filing-indicator template level or "
        "taxonomy expansion regressed"
    )
