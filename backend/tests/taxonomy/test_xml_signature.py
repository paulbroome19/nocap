"""The resolver's xBRL-XML signature assembly (metric + scenario) from DPM."""

from __future__ import annotations

from pathlib import Path

from app.taxonomy.service import TaxonomyLookup


def test_resolve_carries_property_and_context(mini_dpm: Path) -> None:
    with TaxonomyLookup(mini_dpm) as lk:
        res = lk.resolve("C_67.00.a", "0020", "0060", release_id=2)
    assert res is not None
    assert res.datapoint_id == 9900  # dp{VariableID}
    assert res.property_id == 800  # the metric Property
    assert res.context_id == 700  # the dimensional context


def test_xml_signature_metric_and_scenario(mini_dpm: Path) -> None:
    with TaxonomyLookup(mini_dpm) as lk:
        sig = lk.xml_signature(800, 700, release_id=2)
    assert sig is not None
    # Metric element: eba_met:mi900
    assert (sig.metric.prefix, sig.metric.local) == ("eba_met", "mi900")
    assert sig.metric.namespace == "http://www.eba.europa.eu/xbrl/crr/dict/met"

    # Two explicit members, in Context.Signature order.
    assert len(sig.members) == 2
    d0, d1 = sig.members
    # DA introduced in release 1 → eba_dim_1.0:DA ; member eba_BA:x1
    assert (d0.dimension.prefix, d0.dimension.local) == ("eba_dim_1.0", "DA")
    assert d0.dimension.namespace.endswith("/dim/1.0")
    assert (d0.member.prefix, d0.member.local) == ("eba_BA", "x1")
    assert d0.member.namespace.endswith("/dom/BA")
    # MC introduced in release 2 → eba_dim_2.0:MC ; member eba_MC:x5
    assert (d1.dimension.prefix, d1.dimension.local) == ("eba_dim_2.0", "MC")
    assert (d1.member.prefix, d1.member.local) == ("eba_MC", "x5")


def test_xml_signature_single_dimension(mini_dpm: Path) -> None:
    with TaxonomyLookup(mini_dpm) as lk:
        sig = lk.xml_signature(801, 701, release_id=2)
    assert sig is not None
    assert sig.metric.local == "mi901"
    assert len(sig.members) == 1
    assert sig.members[0].member.local == "x1"


def test_xml_signature_unknown_metric_returns_none(mini_dpm: Path) -> None:
    with TaxonomyLookup(mini_dpm) as lk:
        assert lk.xml_signature(999999, None, release_id=2) is None
