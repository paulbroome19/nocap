"""Schemas for the generation stage.

Input DTOs for building an xBRL-CSV report package. All values arrive from other
stages (facts, taxonomy) via ``workflows`` — generation imports only ``core``.
See docs/package-notes.md for the package format these map onto.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel


class OutputFormat(enum.StrEnum):
    """The instance serialisation a package is generated in.

    Both formats are produced from the same resolved facts + metadata; the
    choice is per-(regulator, workflow) configuration, not a code branch. See
    docs/xml-notes.md for the xBRL-XML path.
    """

    xbrl_csv = "xbrl_csv"
    xbrl_xml = "xbrl_xml"


class FactInput(BaseModel):
    """One fact to emit. ``template_code`` is the canonical DB form; row/column
    are text (leading zeros preserved); ``value`` is the raw value."""

    template_code: str
    row_code: str
    column_code: str
    value: str


class FilingIndicatorSpec(BaseModel):
    template_code: str  # canonical DB form, e.g. "C_73.00.a"
    reported: bool = True


class PackageMetadata(BaseModel):
    """Everything needed to name the package and fill parameters.csv.

    Assembled by workflows from the snapshot (framework/module/version), the
    indicators&parameters file (LEI, ref date, currency, decimals, indicators),
    and the run (country, scope, creation timestamp).
    """

    # Report subject / scope
    entity_lei: str
    scope: str = "CON"  # CON | IND | CRDLIQSUBGRP ...
    country: str  # ISO 2-letter

    reference_date: date
    creation_timestamp: str  # YYYYMMDDhhmmssfff (17 digits) — an input, for determinism

    # Module identity (from the snapshot)
    framework_code: str  # e.g. "COREP"
    module_code: str  # e.g. "COREP_LCR_DA"
    module_version: str  # e.g. "3.3.0"
    taxonomy_version: str  # e.g. "4.2"

    # parameters.csv
    base_currency: str  # e.g. "EUR"
    decimals: int  # monetary decimals; other types use standard defaults

    # Optional explicit entry-point URL; derived from the fields above if unset.
    entry_point_url: str | None = None

    filing_indicators: list[FilingIndicatorSpec]


@dataclass
class GeneratedPackage:
    """A built package: the zip bytes plus a small summary."""

    filename: str
    content: bytes
    fact_count: int
    templates: list[str]
