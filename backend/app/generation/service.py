"""Business logic for the generation stage.

Build a submission-ready **xBRL-CSV report package** (zip) from resolved facts,
deterministically (same inputs + same snapshot ⇒ byte-identical zip). See
docs/package-notes.md for the format, naming, and byte conventions.

Everything from other stages arrives injected — generation imports only
``core``:

- ``resolve(template, row, column) -> Resolution | None`` (from taxonomy): the
  datapoint id (``dp{id}``) and its datatype code.
- ``PackageMetadata`` (assembled by workflows from snapshot + params + run).
- an output-store callback (from facts) to persist the zip as a ``RunFile``.
"""

from __future__ import annotations

import io
import json
import zipfile
from collections import defaultdict
from collections.abc import Callable, Sequence
from typing import Protocol

from app.core.errors import ValidationError
from app.generation.schemas import (
    FactInput,
    GeneratedPackage,
    PackageMetadata,
)

# --- injected interfaces ---------------------------------------------------


class Resolution(Protocol):
    """What a resolver returns for a (template, row, column) triple."""

    datapoint_id: int
    datatype_code: str


TemplateResolver = Callable[[str, str, str], "Resolution | None"]


# --- constants -------------------------------------------------------------

# Fixed zip entry timestamp so archives are byte-stable (not `now()`).
_ZIP_DATE_TIME = (1980, 1, 1, 0, 0, 0)
_CRLF = "\r\n"

_REPORT_PACKAGE_JSON = json.dumps(
    {"documentInfo": {"documentType": "https://xbrl.org/report-package/2023"}},
    indent=2,
).encode("utf-8")

# datatype code -> the parameters.csv decimals key it needs.
_DECIMALS_PARAM = {
    "m": "decimalsMonetary",
    "p": "decimalsPercentage",
    "i": "decimalsInteger",
    "r": "decimalsDecimal",
}
# Standard decimals for non-monetary types (monetary uses the supplied value).
_DECIMALS_DEFAULT = {
    "decimalsPercentage": 4,
    "decimalsInteger": 0,
    "decimalsDecimal": 2,
}


# --- naming / URL derivation ----------------------------------------------


def module_version_6(version: str) -> str:
    """'3.3.0' -> '030300' (each of X.Y.Z zero-padded to 2 digits)."""
    parts = version.split(".")
    if not all(p.isdigit() for p in parts) or not parts:
        raise ValidationError(f"invalid module version {version!r}")
    parts = (parts + ["0", "0", "0"])[:3]
    return "".join(p.zfill(2) for p in parts)


def framework_taxonomy_version(version: str) -> str:
    """The framework taxonomy version used in EBA entry-point URLs — the
    major.minor of a DPM release code.

    EBA versions the taxonomy at the framework level (X.Y, e.g. "4.2"). A DPM
    *revision* (X.Y.Z, e.g. "4.2.1") published on the same framework page reuses
    that X.Y taxonomy: every module entry point in the 4.2 package lives at
    ``.../fws/{framework}/4.2/mod/...`` — never ``.../4.2.1/...``. So the URL
    segment is the major.minor of the release code; using the full revision
    yields entry points that do not exist (``xbrlce:unresolvableBaseMetadataFile``).
    """
    parts = version.split(".")
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        return f"{parts[0]}.{parts[1]}"
    return version  # already X.Y, or not numeric — use verbatim


def entry_point_url(md: PackageMetadata, *, extension: str = "json") -> str:
    """Explicit URL if given (and matching the extension), else the EBA pattern.

    ``extension`` is ``json`` for xBRL-CSV and ``xsd`` for xBRL-XML — the same
    module entry point, different file. The version segment is the *framework*
    taxonomy version (major.minor), so a 4.2.1 DPM resolves against its 4.2
    taxonomy package (see ``framework_taxonomy_version``).
    """
    if md.entry_point_url and md.entry_point_url.endswith(f".{extension}"):
        return md.entry_point_url
    return (
        "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/"
        f"{md.framework_code.lower()}/"
        f"{framework_taxonomy_version(md.taxonomy_version)}/mod/"
        f"{md.module_code.lower()}.{extension}"
    )


def report_name(md: PackageMetadata) -> str:
    """The package base name (also the zip's root folder), per Filing Rules."""
    subject = f"{md.entity_lei}.{md.scope}"
    fw_mod_ver = f"{md.framework_code.upper()}{module_version_6(md.module_version)}"
    module_token = md.module_code.replace("_", "").upper()
    return (
        f"{subject}_{md.country}_{fw_mod_ver}_{module_token}"
        f"_{md.reference_date.isoformat()}_{md.creation_timestamp}"
    )


# --- CSV / JSON rendering --------------------------------------------------


def _csv_field(value: str) -> str:
    """OIM/RFC-4180 quoting: quote if the value has , CR LF or ", doubling \"."""
    if any(c in value for c in (",", "\r", "\n", '"')):
        return '"' + value.replace('"', '""') + '"'
    return value


def _csv_bytes(rows: Sequence[Sequence[str]]) -> bytes:
    """Render rows as CRLF-terminated CSV (incl. trailing CRLF), UTF-8."""
    lines = [",".join(_csv_field(c) for c in row) for row in rows]
    return (_CRLF.join(lines) + _CRLF).encode("utf-8")


def _report_json_bytes(url: str) -> bytes:
    return json.dumps(
        {
            "documentInfo": {
                "documentType": "https://xbrl.org/2021/xbrl-csv",
                "extends": [url],
            }
        },
        indent=2,
    ).encode("utf-8")


def _parameters_rows(
    md: PackageMetadata, datatypes: set[str]
) -> list[list[str]]:
    rows: list[list[str]] = [
        ["name", "value"],
        ["entityID", f"rs:{md.entity_lei}.{md.scope}"],
        ["refPeriod", md.reference_date.isoformat()],
    ]
    # baseCurrency only if a fact refers to it (any monetary fact).
    if "m" in datatypes:
        rows.append(["baseCurrency", f"iso4217:{md.base_currency}"])
    # decimals params only for the metric types actually present.
    for code in ("m", "p", "i", "r"):
        if code not in datatypes:
            continue
        param = _DECIMALS_PARAM[code]
        value = md.decimals if code == "m" else _DECIMALS_DEFAULT[param]
        rows.append([param, str(value)])
    return rows


def _filing_indicators_rows(md: PackageMetadata) -> list[list[str]]:
    rows: list[list[str]] = [["templateID", "reported"]]
    for fi in sorted(md.filing_indicators, key=lambda f: f.template_code):
        rows.append([fi.template_code, "true" if fi.reported else "false"])
    return rows


# --- zip assembly ----------------------------------------------------------


def _zip_bytes(files: list[tuple[str, bytes]]) -> bytes:
    """Deterministic zip: fixed timestamps, fixed order, fixed permissions."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in files:
            info = zipfile.ZipInfo(path, date_time=_ZIP_DATE_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, content)
    return buf.getvalue()


# --- public API ------------------------------------------------------------


def build_package(
    facts: Sequence[FactInput],
    metadata: PackageMetadata,
    *,
    resolve: TemplateResolver,
    strict: bool = True,
) -> GeneratedPackage:
    """Resolve facts to datapoints and assemble the xBRL-CSV package zip.

    ``strict`` (default): raise ``ValidationError`` (with details) if any fact
    fails to resolve or a template has two facts for the same datapoint with
    different values. ``strict=False``: skip unresolved facts and keep the first
    value on a conflict, so a package is always produced for inspection — the
    caller (workflows) reports those problems as validation findings instead.
    """
    # template code -> {datapoint_id: value}
    by_template: dict[str, dict[int, str]] = defaultdict(dict)
    datatypes: set[str] = set()
    unresolved: list[dict[str, str]] = []
    conflicts: list[dict[str, str]] = []

    for fact in facts:
        res = resolve(fact.template_code, fact.row_code, fact.column_code)
        if res is None:
            unresolved.append(
                {
                    "template": fact.template_code,
                    "row": fact.row_code,
                    "column": fact.column_code,
                }
            )
            continue
        cell = by_template[fact.template_code]
        if res.datapoint_id in cell and cell[res.datapoint_id] != fact.value:
            conflicts.append(
                {"template": fact.template_code, "datapoint": str(res.datapoint_id)}
            )
            continue
        cell[res.datapoint_id] = fact.value
        datatypes.add(res.datatype_code)

    if strict and unresolved:
        raise ValidationError(
            "facts do not resolve to datapoints in the bound snapshot",
            details=unresolved,
        )
    if strict and conflicts:
        raise ValidationError(
            "conflicting values for the same datapoint", details=conflicts
        )

    root = report_name(metadata)
    files: list[tuple[str, bytes]] = [
        (f"{root}/META-INF/reportPackage.json", _REPORT_PACKAGE_JSON),
        (
            f"{root}/reports/FilingIndicators.csv",
            _csv_bytes(_filing_indicators_rows(metadata)),
        ),
        (
            f"{root}/reports/parameters.csv",
            _csv_bytes(_parameters_rows(metadata, datatypes)),
        ),
        (
            f"{root}/reports/report.json",
            _report_json_bytes(entry_point_url(metadata)),
        ),
    ]
    # One CSV per template, templates sorted; rows sorted by datapoint id.
    for template in sorted(by_template):
        cell = by_template[template]
        rows: list[list[str]] = [["datapoint", "factValue"]]
        for datapoint_id in sorted(cell):
            rows.append([f"dp{datapoint_id}", cell[datapoint_id]])
        files.append(
            (f"{root}/reports/{template.lower()}.csv", _csv_bytes(rows))
        )

    return GeneratedPackage(
        filename=f"{root}.zip",
        content=_zip_bytes(files),
        fact_count=sum(len(c) for c in by_template.values()),
        templates=sorted(by_template),
    )


# Injected store: (db, run_id, filename, data) -> the persisted RunFile. The
# composition root / workflows binds this to facts' store_run_file with
# role=package_output (generation must not import the facts stage).
PackageStore = Callable[[object, int, str, bytes], object]


def store_package(
    db: object,
    *,
    run_id: int,
    package: GeneratedPackage,
    store: PackageStore,
) -> object:
    """Persist a built package as a run's ``package_output`` file."""
    return store(db, run_id, package.filename, package.content)
