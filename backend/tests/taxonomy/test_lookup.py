"""Lookup contract against the mini DPM fixture."""

from __future__ import annotations

from pathlib import Path

from app.taxonomy.service import TaxonomyLookup


def test_resolve_returns_datapoint_and_datatype(mini_dpm: Path) -> None:
    with TaxonomyLookup(mini_dpm) as lk:
        res = lk.resolve("C_67.00.a", "0020", "0060")
    assert res is not None
    assert res.datapoint_id == 9900  # VariableID (the xBRL property-group key)
    assert res.datatype_code == "m"
    assert res.datatype_name == "monetary"
    assert res.period_type == "Stock"
    assert res.cell_code == "{C_67.00.a, r0020, c0060, s0010}"


def test_resolve_accepts_all_template_forms(mini_dpm: Path) -> None:
    with TaxonomyLookup(mini_dpm) as lk:
        ids = {
            lk.resolve(code, "0020", "0060").datapoint_id
            for code in ("C_67.00.a", "C_67_00_a", "C 67.00.a")
        }
    assert ids == {9900}


def test_resolve_second_datapoint_percentage(mini_dpm: Path) -> None:
    with TaxonomyLookup(mini_dpm) as lk:
        res = lk.resolve("C_67.00.a", "0010", "0010")
    assert res is not None
    assert res.datapoint_id == 9901  # VariableID
    assert res.datatype_code == "p"


def test_leading_zeros_are_significant(mini_dpm: Path) -> None:
    """'20' must not match the '0020' row code."""
    with TaxonomyLookup(mini_dpm) as lk:
        assert lk.resolve("C_67.00.a", "20", "0060") is None
        assert lk.resolve("C_67.00.a", "0020", "60") is None


def test_unknown_triples_return_none(mini_dpm: Path) -> None:
    with TaxonomyLookup(mini_dpm) as lk:
        assert lk.resolve("C_99.99", "0010", "0010") is None  # no such template
        assert lk.resolve("C_67.00.a", "9990", "0060") is None  # no such row
        assert lk.resolve("not-a-code", "0010", "0010") is None  # unparseable


def test_release_binding_defaults_to_current_and_dedupes(mini_dpm: Path) -> None:
    """Column 0060 is versioned in two windows; current release yields one row."""
    with TaxonomyLookup(mini_dpm) as lk:
        assert lk.default_release_id() == 2
        res = lk.resolve("C_67.00.a", "0020", "0060")  # defaults to release 2
        assert res is not None and res.datapoint_id == 9900
        # Explicit older release also resolves (older header window).
        res1 = lk.resolve("C_67.00.a", "0020", "0060", release_id=1)
        assert res1 is not None and res1.datapoint_id == 9900


def test_list_templates_for_module(mini_dpm: Path) -> None:
    with TaxonomyLookup(mini_dpm) as lk:
        codes = [t.code for t in lk.list_templates("COREP_LCR_DA")]
    assert codes == ["C_67.00.a", "C_72.00.a", "C_77.00"]


def test_open_templates(mini_dpm: Path) -> None:
    with TaxonomyLookup(mini_dpm) as lk:
        # C_77.00 has KeyID set (open); the others are closed.
        assert lk.open_templates("COREP_LCR_DA") == {"C_77.00"}


def test_list_templates_unknown_module_is_empty(mini_dpm: Path) -> None:
    with TaxonomyLookup(mini_dpm) as lk:
        assert lk.list_templates("NOPE") == []
