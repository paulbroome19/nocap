"""Build a submission-ready **xBRL-XML instance** (zip) from resolved facts.

A second output format alongside the xBRL-CSV package (``service.py``), from the
same facts + metadata + resolver. See docs/xml-notes.md for the format and the
DPM→XML context-assembly recipe.

Deterministic (same inputs + same snapshot ⇒ byte-identical zip): contexts,
units, facts and namespaces are all sorted; ids are short and non-semantic
(rule 2.6); zip timestamps are fixed; the software processing instruction (rule
2.26) is a fixed literal.

Generation imports only ``core``; the xBRL-XML signature of each datapoint
arrives through the injected ``resolve`` callback (an ``XmlResolution``).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol
from xml.sax.saxutils import escape, quoteattr

from app.core.errors import ValidationError
from app.generation.schemas import FactInput, GeneratedPackage, PackageMetadata
from app.generation.service import _zip_bytes, entry_point_url, report_name

# --- injected interface ----------------------------------------------------


class XmlName(Protocol):
    prefix: str
    namespace: str
    local: str


class XmlMemberLike(Protocol):
    dimension: XmlName
    member: XmlName


class XmlResolution(Protocol):
    """The xBRL-XML signature of a resolved datapoint (from taxonomy)."""

    metric: XmlName
    members: Sequence[XmlMemberLike]
    datatype_code: str


XmlResolver = Callable[[str, str, str], "XmlResolution | None"]


# --- constants -------------------------------------------------------------

_ENTITY_SCHEME = "https://eurofiling.info/eu/rs"  # Filing Rule 5.2
_CRLF = "\r\n"

# Fixed core namespaces (prefix -> URI). EBA met/dim/dom namespaces are added
# per the facts actually present.
_CORE_NS = {
    "xbrli": "http://www.xbrl.org/2003/instance",
    "xbrldi": "http://xbrl.org/2006/xbrldi",
    "xlink": "http://www.w3.org/1999/xlink",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
    "link": "http://www.xbrl.org/2003/linkbase",
    "iso4217": "http://www.xbrl.org/2003/iso4217",
    "find": "http://www.eurofiling.info/xbrl/ext/filing-indicators",
}

# datatype code -> (unit measure, unit id) or None (non-numeric ⇒ no unit).
_PURE = ("xbrli:pure", "uPURE")
_UNIT_BY_DATATYPE = {
    "m": None,  # monetary: currency unit assigned from base currency
    "p": _PURE,
    "r": _PURE,
    "i": _PURE,
}
_NUMERIC = {"m", "p", "r", "i"}
# Non-monetary numeric decimals (monetary uses the metadata value).
_DECIMALS_DEFAULT = {"p": 4, "i": 0, "r": 2}


# --- helpers ---------------------------------------------------------------


def _qname(name: XmlName) -> str:
    return f"{name.prefix}:{name.local}"


def _member_key(m: XmlMemberLike) -> tuple[str, str]:
    return (_qname(m.dimension), _qname(m.member))


def _scenario_key(members: Sequence[XmlMemberLike]) -> tuple[tuple[str, str], ...]:
    """Order-independent identity of a scenario (for context de-duplication)."""
    return tuple(sorted(_member_key(m) for m in members))


class _Resolved:
    """A fact paired with its resolved signature, unit, and decimals."""

    __slots__ = ("value", "res", "unit_id", "decimals")

    def __init__(self, value: str, res: XmlResolution, currency: str, dec: int):
        self.value = value
        self.res = res
        code = res.datatype_code
        if code == "m":
            self.unit_id: str | None = f"u{currency}"
            self.decimals: int | None = dec
        elif code in _UNIT_BY_DATATYPE:
            self.unit_id = _PURE[1]
            self.decimals = _DECIMALS_DEFAULT[code]
        else:  # non-numeric: no unit, no decimals
            self.unit_id = None
            self.decimals = None


def _collect_namespaces(resolved: list[_Resolved]) -> dict[str, str]:
    ns = dict(_CORE_NS)
    for r in resolved:
        for name in (r.res.metric, *[m.dimension for m in r.res.members],
                     *[m.member for m in r.res.members]):
            ns[name.prefix] = name.namespace
    return ns


def _units(resolved: list[_Resolved], currency: str) -> list[tuple[str, str]]:
    """Distinct (unit id, measure) actually referenced, sorted by id."""
    used: dict[str, str] = {}
    for r in resolved:
        if r.unit_id is None:
            continue
        used[r.unit_id] = (
            f"iso4217:{currency}" if r.res.datatype_code == "m" else _PURE[0]
        )
    return sorted(used.items())


# --- public API ------------------------------------------------------------


def build_xml_instance(
    facts: Sequence[FactInput],
    metadata: PackageMetadata,
    *,
    resolve: XmlResolver,
    strict: bool = True,
) -> GeneratedPackage:
    """Resolve facts to xBRL-XML and assemble the instance zip.

    ``strict`` mirrors the CSV builder: raise on unresolved facts / conflicts,
    else skip them and let the caller report findings. A fact whose datapoint
    has no XML signature (e.g. a typed/open-table key) is treated as unresolved.
    """
    currency = metadata.base_currency
    dec_monetary = metadata.decimals

    # datapoint identity for conflict detection = (metric qname + scenario key).
    seen: dict[tuple, str] = {}
    resolved: list[_Resolved] = []
    templates: set[str] = set()
    unresolved: list[dict[str, str]] = []
    conflicts: list[dict[str, str]] = []

    for fact in facts:
        res = resolve(fact.template_code, fact.row_code, fact.column_code)
        if res is None:
            unresolved.append({
                "template": fact.template_code,
                "row": fact.row_code,
                "column": fact.column_code,
            })
            continue
        key = (_qname(res.metric), _scenario_key(res.members))
        if key in seen and seen[key] != fact.value:
            conflicts.append(
                {"template": fact.template_code, "metric": _qname(res.metric)}
            )
            continue
        if key in seen:
            continue
        seen[key] = fact.value
        templates.add(fact.template_code)
        resolved.append(_Resolved(fact.value, res, currency, dec_monetary))

    if strict and unresolved:
        raise ValidationError(
            "facts do not resolve to xBRL-XML datapoints in the bound snapshot",
            details=unresolved,
        )
    if strict and conflicts:
        raise ValidationError(
            "conflicting values for the same datapoint", details=conflicts
        )

    xml = _render(resolved, metadata, currency)
    root = report_name(metadata)
    package = _zip_bytes([(f"{root}.xbrl", xml.encode("utf-8"))])
    return GeneratedPackage(
        filename=f"{root}.zip",
        content=package,
        fact_count=len(resolved),
        templates=sorted(templates),
    )


def _render(resolved: list[_Resolved], md: PackageMetadata, currency: str) -> str:
    entity = f"{md.entity_lei}.{md.scope}"
    ref_date = md.reference_date.isoformat()

    # Assign short non-semantic context ids (rule 2.6), sorted by scenario.
    scenarios: dict[tuple, Sequence[XmlMemberLike]] = {}
    for r in resolved:
        scenarios.setdefault(_scenario_key(r.res.members), r.res.members)
    ctx_id = {key: f"c{i + 1}" for i, key in enumerate(sorted(scenarios))}

    namespaces = _collect_namespaces(resolved)
    units = _units(resolved, currency)

    lines: list[str] = []
    lines.append("<?xml version='1.0' encoding='UTF-8'?>")
    # Software info (rule 2.26) — deterministic: creationdate from the run's
    # creation timestamp (YYYYMMDDhhmmssfff), an input, not now().
    ts = md.creation_timestamp
    created = (
        f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}T{ts[8:10]}:{ts[10:12]}:{ts[12:14]}"
        if len(ts) >= 14
        else ref_date
    )
    lines.append(
        f'<?instance-generator id="carter" version="0.1.0" '
        f'creationdate="{created}"?>'
    )
    ns_attrs = " ".join(
        f'xmlns:{p}={quoteattr(namespaces[p])}' for p in sorted(namespaces)
    )
    lines.append(f"<xbrli:xbrl {ns_attrs}>")

    # schemaRef (rules 2.2, 2.3) — exactly one, absolute, .xsd.
    href = entry_point_url(md, extension="xsd")
    lines.append(
        f'  <link:schemaRef xlink:type="simple" xlink:href={quoteattr(href)}/>'
    )

    # Units (sorted).
    for uid, measure in units:
        lines.append(f'  <xbrli:unit id="{uid}">')
        lines.append(f"    <xbrli:measure>{escape(measure)}</xbrli:measure>")
        lines.append("  </xbrli:unit>")

    # Filing-indicator context (entity + period, no scenario) + fIndicators.
    lines += _context_block("cfi", entity, ref_date, ())
    lines.append("  <find:fIndicators>")
    for fi in sorted(md.filing_indicators, key=lambda f: f.template_code):
        filed = "true" if fi.reported else "false"
        lines.append(
            f'    <find:filingIndicator contextRef="cfi" '
            f'find:filed="{filed}">{escape(fi.template_code)}</find:filingIndicator>'
        )
    lines.append("  </find:fIndicators>")

    # Data contexts (sorted by id).
    for key in sorted(scenarios):
        lines += _context_block(ctx_id[key], entity, ref_date, scenarios[key])

    # Facts, sorted by (metric qname, context id).
    def fact_sort(r: _Resolved) -> tuple[str, str]:
        return (_qname(r.res.metric), ctx_id[_scenario_key(r.res.members)])

    for r in sorted(resolved, key=fact_sort):
        cid = ctx_id[_scenario_key(r.res.members)]
        attrs = f'contextRef="{cid}"'
        if r.unit_id is not None:
            attrs += f' unitRef="{r.unit_id}"'
        if r.decimals is not None:
            attrs += f' decimals="{r.decimals}"'
        el = _qname(r.res.metric)
        lines.append(f"  <{el} {attrs}>{escape(r.value)}</{el}>")

    lines.append("</xbrli:xbrl>")
    return _CRLF.join(lines) + _CRLF


def _context_block(
    cid: str, entity: str, ref_date: str, members: Sequence[XmlMemberLike]
) -> list[str]:
    out = [
        f'  <xbrli:context id="{cid}">',
        "    <xbrli:entity>",
        f'      <xbrli:identifier scheme="{_ENTITY_SCHEME}">'
        f"{escape(entity)}</xbrli:identifier>",
        "    </xbrli:entity>",
        "    <xbrli:period>",
        f"      <xbrli:instant>{ref_date}</xbrli:instant>",
        "    </xbrli:period>",
    ]
    if members:
        out.append("    <xbrli:scenario>")
        # Scenario members sorted deterministically (by dimension, then member).
        for m in sorted(members, key=_member_key):
            out.append(
                f'      <xbrldi:explicitMember dimension="{_qname(m.dimension)}">'
                f"{_qname(m.member)}</xbrldi:explicitMember>"
            )
        out.append("    </xbrli:scenario>")
    out.append("  </xbrli:context>")
    return out
