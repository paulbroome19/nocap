"""Compare our generated xBRL-XML instance's structure to a real EBA sample.

The committed fixture ``sample_xbrl_xml_instance.xbrl`` is a real EBA illustrative
sample (fictional DUMMYLEI, random data) for the PILLAR3 IRRBBDIS module — a
different framework than our COREP LCR output, so we compare *structure*, not
bytes: root/namespaces, schemaRef, context/unit/fact/filing-indicator grammar.
"""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from app.generation.schemas import FilingIndicatorSpec
from app.generation.xml_builder import build_xml_instance
from tests.generation._helpers import (
    dim,
    fi,
    mem,
    met,
    metadata,
    open_zip,
    xml_res,
    xml_resolver,
)

SAMPLE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "sample_xbrl_xml_instance.xbrl"
)

XBRLI = "http://www.xbrl.org/2003/instance"
XBRLDI = "http://xbrl.org/2006/xbrldi"
FIND = "http://www.eurofiling.info/xbrl/ext/filing-indicators"
LINK = "http://www.xbrl.org/2003/linkbase"
MET = "http://www.eba.europa.eu/xbrl/crr/dict/met"
ENTITY_SCHEME = "https://eurofiling.info/eu/rs"


def _build_ours() -> bytes:
    # Two facts sharing a metric but different scenarios, plus a monetary + pure.
    from tests.generation._helpers import _Member

    m1 = met("mi500")
    d_prp = dim("3.4", "PRP")
    facts = [fi("C_72.00.a", "0010", "0010", "1000")]
    resmap = {
        ("C_72.00.a", "0010", "0010"): xml_res(
            m1, [_Member(d_prp, mem("PL", "x11"))], "m"
        ),
    }
    md = metadata(
        filing_indicators=[
            FilingIndicatorSpec(template_code="C_72.00.a", reported=True),
            FilingIndicatorSpec(template_code="C_73.00.a", reported=False),
        ]
    )
    pkg = build_xml_instance(facts, md, resolve=xml_resolver(resmap), strict=True)
    return open_zip(pkg.content).read(pkg.filename[:-4] + ".xbrl")


def _structure(xml_bytes: bytes) -> dict:
    root = ET.fromstring(xml_bytes)
    assert root.tag == f"{{{XBRLI}}}xbrl"
    schemarefs = root.findall(f"{{{LINK}}}schemaRef")
    href = schemarefs[0].get("{http://www.w3.org/1999/xlink}href")
    units = root.findall(f"{{{XBRLI}}}unit")
    contexts = root.findall(f"{{{XBRLI}}}context")
    findicators = root.find(f"{{{FIND}}}fIndicators")
    # A data context = one with a scenario.
    scen_ctx = [c for c in contexts if c.find(f"{{{XBRLI}}}scenario") is not None]
    # facts = elements in the eba_met namespace.
    facts = [e for e in root if e.tag.startswith(f"{{{MET}}}")]

    filed_attrs = set()
    fi_els = []
    if findicators is not None:
        fi_els = findicators.findall(f"{{{FIND}}}filingIndicator")
        for f in fi_els:
            filed_attrs.add(f.get(f"{{{FIND}}}filed"))

    # explicitMember shape from the first scenario.
    em = None
    if scen_ctx:
        em = scen_ctx[0].find(
            f"{{{XBRLI}}}scenario/{{{XBRLDI}}}explicitMember"
        )
    return {
        "schemaref_count": len(schemarefs),
        "schemaref_ext": href.rsplit(".", 1)[-1] if href else None,
        "unit_measures": {
            u.find(f"{{{XBRLI}}}measure").text for u in units
        },
        "entity_scheme": contexts[0]
        .find(f"{{{XBRLI}}}entity/{{{XBRLI}}}identifier")
        .get("scheme"),
        "has_instant": contexts[0].find(f"{{{XBRLI}}}period/{{{XBRLI}}}instant")
        is not None,
        "fi_count": len(fi_els),
        "filed_present": (
            all(v is not None for v in filed_attrs) if filed_attrs else False
        ),
        "explicit_member_has_dim": em is not None
        and em.get("dimension") is not None,
        "explicit_member_value_qname": (
            (":" in (em.text or "")) if em is not None else False
        ),
        "fact_has_contextref": (
            all(f.get("contextRef") for f in facts) if facts else False
        ),
    }


def test_our_xml_structure_matches_sample() -> None:
    sample = _structure(SAMPLE.read_bytes())
    ours = _structure(_build_ours())

    # schemaRef: exactly one, .xsd (rules 2.2/2.3).
    assert sample["schemaref_count"] == ours["schemaref_count"] == 1
    assert sample["schemaref_ext"] == ours["schemaref_ext"] == "xsd"

    # Entity scheme + instant period (rules 5.2, 2.10).
    assert ours["entity_scheme"] == sample["entity_scheme"] == ENTITY_SCHEME
    assert ours["has_instant"] and sample["has_instant"]

    # Units: our measures are a subset of the sample's grammar (pure/EUR).
    assert ours["unit_measures"] <= {"iso4217:EUR", "xbrli:pure"}
    assert sample["unit_measures"] <= {"iso4217:EUR", "xbrli:pure"}

    # Filing indicators present with the find:filed attribute.
    assert ours["fi_count"] >= 1 and sample["fi_count"] >= 1
    assert ours["filed_present"]  # we always emit find:filed

    # Scenario explicit-member grammar: dimension attr + prefixed member value.
    assert ours["explicit_member_has_dim"] and sample["explicit_member_has_dim"]
    assert ours["explicit_member_value_qname"] and sample["explicit_member_value_qname"]

    # Facts reference a context.
    assert ours["fact_has_contextref"] and sample["fact_has_contextref"]


def test_our_instance_is_well_formed_and_deterministic() -> None:
    a = _build_ours()
    b = _build_ours()
    assert a == b  # byte-identical across builds
    ET.fromstring(a)  # well-formed
