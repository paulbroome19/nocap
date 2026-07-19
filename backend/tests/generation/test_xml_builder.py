"""Unit tests for the xBRL-XML instance builder."""

from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest

from app.core.errors import ValidationError
from app.generation.xml_builder import build_xml_instance
from tests.generation._helpers import (
    _Member,
    dim,
    fi,
    mem,
    met,
    metadata,
    open_zip,
    xml_res,
    xml_resolver,
)

MET = "http://www.eba.europa.eu/xbrl/crr/dict/met"
XBRLI = "http://www.xbrl.org/2003/instance"


def _instance(pkg) -> bytes:
    return open_zip(pkg.content).read(pkg.filename[:-4] + ".xbrl")


def _facts_and_map():
    facts = [
        fi("C_72.00.a", "0010", "0010", "1000"),
        fi("C_72.00.a", "0020", "0010", "2000"),  # same scenario as first → shares ctx
        fi("C_76.00.a", "0010", "0010", "0.5"),  # pure, different scenario
    ]
    m = _Member(dim("3.4", "PRP"), mem("PL", "x11"))
    resmap = {
        ("C_72.00.a", "0010", "0010"): xml_res(met("mi1"), [m], "m"),
        # same scenario (same members) → shares the context:
        ("C_72.00.a", "0020", "0010"): xml_res(met("mi2"), [m], "m"),
        ("C_76.00.a", "0010", "0010"): xml_res(
            met("mi3"), [_Member(dim("4.0", "qCAA"), mem("qAI", "qx1"))], "p"
        ),
    }
    return facts, resmap


def test_contexts_deduplicate_by_scenario() -> None:
    facts, resmap = _facts_and_map()
    pkg = build_xml_instance(facts, metadata(), resolve=xml_resolver(resmap))
    root = ET.fromstring(_instance(pkg))
    contexts = root.findall(f"{{{XBRLI}}}context")
    # cfi + two data contexts (two distinct scenarios; the first two facts share one).
    scen = [c for c in contexts if c.find(f"{{{XBRLI}}}scenario") is not None]
    assert len(scen) == 2
    facts_els = [e for e in root if e.tag.startswith(f"{{{MET}}}")]
    assert len(facts_els) == 3


def test_units_only_referenced_ones() -> None:
    facts, resmap = _facts_and_map()
    pkg = build_xml_instance(facts, metadata(), resolve=xml_resolver(resmap))
    root = ET.fromstring(_instance(pkg))
    measures = {
        u.find(f"{{{XBRLI}}}measure").text
        for u in root.findall(f"{{{XBRLI}}}unit")
    }
    assert measures == {"iso4217:EUR", "xbrli:pure"}


def test_strict_raises_on_unresolved() -> None:
    facts = [fi("C_99.99.z", "0010", "0010", "1")]
    with pytest.raises(ValidationError, match="do not resolve"):
        build_xml_instance(facts, metadata(), resolve=xml_resolver({}), strict=True)


def test_non_strict_skips_unresolved() -> None:
    facts, resmap = _facts_and_map()
    facts.append(fi("C_99.99.z", "0010", "0010", "1"))  # unresolved
    pkg = build_xml_instance(
        facts, metadata(), resolve=xml_resolver(resmap), strict=False
    )
    assert pkg.fact_count == 3  # the unresolved one skipped
    ET.fromstring(_instance(pkg))
