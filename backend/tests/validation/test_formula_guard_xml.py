"""Permanent guard for the xBRL-XML formula-validation path (CP5 / Step 3).

The xBRL-CSV path has its own guard (test_formula_guard). This is the twin for
the xBRL-XML output format: it generates an instance the app's way — the real
DPM→XML signature recipe (metric + release-versioned dimensions), the real
filing-indicator collapse — and asserts the same Arelle oracle that caught the
three CSV bugs (a) loads the instance with ZERO unknownPropertyGroup errors and
(b) evaluates at least one assertion bound to a generated fact.

It pins the recipe against real COREP LCR data (not just the Pillar 3 sample the
recipe was first derived on), so a regression in the metric/dimension namespaces
or the context assembly is caught end-to-end.

Integration test: needs Arelle, the real EBA 4.2 DPM (with the dimensional
projection — ItemCategory/Context) and the taxonomy package under the data dir.
It re-projects those two tables from the stored Access source when a legacy
pre-dimensional dpm.sqlite is all that is present; otherwise it skips cleanly.
"""

from __future__ import annotations

import io
import sqlite3
import zipfile
from datetime import date
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.facts.schemas import FilingIndicator
from app.generation.schemas import FactInput, FilingIndicatorSpec, PackageMetadata
from app.generation.xml_builder import build_xml_instance
from app.taxonomy import service as taxonomy
from app.workflows.service import _make_xml_resolver, _template_level_indicators

pytest.importorskip("arelle")

_MODULE = "COREP_LCR_DA"
_TABLES = ("C_72.00.a", "C_76.00.a", "C_76.00.b")
_REAL_DATA = Path(__file__).resolve().parents[2] / "data"


def _has_table(dpm: Path, table: str) -> bool:
    conn = sqlite3.connect(f"file:{dpm}?mode=ro", uri=True)
    try:
        return bool(
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
        )
    finally:
        conn.close()


def _dimensional_dpm() -> Path | None:
    """A projected DPM carrying the dimensional tables, or None to skip.

    Uses the snapshot's dpm.sqlite when it already has them; else re-projects
    from the stored Access source (cached) so a legacy snapshot still runs.
    """
    snap = _REAL_DATA / "snapshots" / "1"
    dpm = snap / "dpm.sqlite"
    if dpm.exists() and _has_table(dpm, "ItemCategory"):
        return dpm
    source = snap / "source.accdb"
    if not source.exists():
        return None
    cached = _REAL_DATA / "cache" / "dpm_dimensional.sqlite"
    if not (cached.exists() and _has_table(cached, "ItemCategory")):
        cached.parent.mkdir(parents=True, exist_ok=True)
        try:
            taxonomy.convert_accdb_to_sqlite(
                source, cached, settings=get_settings()
            )
        except taxonomy.ConversionError:
            return None
    return cached


def _enum_cells(dpm: Path) -> list[tuple[str, str, str]]:
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
def test_generated_xml_instance_loads_and_assertions_evaluate() -> None:
    dpm = _dimensional_dpm()
    taxo = sorted(
        (_REAL_DATA / "snapshots" / "1" / "taxonomy").glob("*.zip")
    )
    if dpm is None or not taxo:
        pytest.skip("real EBA 4.2 DPM (dimensional) + taxonomy package not present")
    cache = _REAL_DATA / "cache"
    cache.mkdir(parents=True, exist_ok=True)

    cells = _enum_cells(dpm)
    assert cells, "expected C_72/C_76 cells in the DPM"

    with taxonomy.TaxonomyLookup(dpm) as lk:
        rid = lk.default_release_id()
        meta = lk.module_metadata(_MODULE, release_id=rid)

        def resolve(t, r, c):
            return lk.resolve(t, r, c, release_id=rid)

        xresolve = _make_xml_resolver(lk, resolve, rid)
        # The recipe must sign the great majority of real COREP cells; a few are
        # legitimately unsignable (no metric property) and are excluded.
        signable = [c for c in cells if xresolve(*c) is not None]
        assert len(signable) >= 0.9 * len(cells), (
            f"only {len(signable)}/{len(cells)} cells produced an XML signature"
        )

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
                FilingIndicatorSpec(
                    template_code=i.template_code, reported=i.reported
                )
                for i in indicators
            ],
        )
        package = build_xml_instance(
            [
                FactInput(template_code=t, row_code=r, column_code=c, value="0")
                for (t, r, c) in cells
            ],
            md, resolve=xresolve, strict=False,
        )

    # A bare xBRL-XML instance loads directly (--file), not as a report package.
    zf = zipfile.ZipFile(io.BytesIO(package.content))
    xbrl_name = next(n for n in zf.namelist() if n.endswith(".xbrl"))
    out = cache / "guard_instance.xbrl"
    out.write_bytes(zf.read(xbrl_name))

    from app.validation.arelle_adapter import ArelleFormulaValidator

    run = ArelleFormulaValidator(cache_dir=cache).validate_detailed(out, taxo)

    # (a) the instance loads — every fact bound to a taxonomy property group.
    assert run.available, run.unavailable_reason
    assert run.unknown_property_groups == 0, (
        f"{run.unknown_property_groups} facts rejected as unknownPropertyGroup — "
        "the DPM→XML metric/dimension namespace recipe regressed"
    )
    # (b) at least one assertion actually evaluated against a generated fact.
    assert len(run.rule_results) >= 1, (
        "no formula assertion evaluated on the XML path — context assembly or "
        "filing-indicator level regressed"
    )
