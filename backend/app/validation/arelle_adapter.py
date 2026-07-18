"""Arelle formula-validation adapter (v2 seam).

Executes the EBA's own XBRL formula rules against a generated package, offline,
and maps Arelle's per-assertion results into our generic ``Finding`` model. The
log→findings mapping is a pure function so it can be tested with canned Arelle
output (CI needs no taxonomy package).

Offline: the EBA taxonomy imports eurofiling.info core files it does not bundle;
those are vendored (see vendor/eurofiling/) and passed to Arelle as an extra
taxonomy package, so nothing ever touches the network.
"""

from __future__ import annotations

import json
import logging
import re
import zipfile
from pathlib import Path
from typing import Protocol

from app.validation.models import Severity, ValidationPhase
from app.validation.schemas import Finding

logger = logging.getLogger(__name__)

_VENDOR_EUROFILING = Path(__file__).parent / "vendor" / "eurofiling"

# EBA deactivated rules (the two named on the EBA page). Seam: extend by loading
# the full deactivated-rules spreadsheet later (see load_deactivated_rules).
DEACTIVATED_RULES_DEFAULT = {"v6272_m", "v23336_m"}

# Arelle log codes for assertion results look like "message:v12729_m_0".
_ASSERTION_CODE = re.compile(r"^message:(v\d+_[a-z]+)(?:_\d+)?$")
# Codes that mean the taxonomy/instance did not load (so 0 assertions is NOT a
# clean pass — e.g. a taxonomy-package version mismatch).
_LOAD_ERROR_CODES = {
    "oime:invalidTaxonomy",
    "xbrlce:unresolvableBaseMetadataFile",
    "arelleOIMloader:error",
    "IOerror",
}
# Cell reference inside an assertion message, e.g. {D_09.01,0020,0030,}.
_CELL_REF = re.compile(r"\{([A-Za-z0-9_.]+),([0-9]+),([0-9]+),")

_LEVEL_TO_SEVERITY = {
    "error": Severity.error,
    "warning": Severity.warning,
    "info": Severity.info,
}


def load_deactivated_rules(extra: set[str] | None = None) -> set[str]:
    """The deactivated-rule ids to drop. Seam for the full spreadsheet later."""
    return set(DEACTIVATED_RULES_DEFAULT) | (extra or set())


_MSG_PREFIX = re.compile(r"^\[message:[^\]]+\]\s*")


def _message_text(record: dict) -> str:
    msg = record.get("message")
    text = str(msg.get("text", "")) if isinstance(msg, dict) else str(msg or "")
    return _MSG_PREFIX.sub("", text).strip()


def _parse_location(text: str) -> dict:
    m = _CELL_REF.search(text)
    if m is None:
        return {}
    return {
        "template_code": m.group(1),
        "row_code": m.group(2),
        "column_code": m.group(3),
    }


def findings_from_arelle_records(
    records: list[dict], *, deactivated_rules: set[str]
) -> list[Finding]:
    """Pure mapping: Arelle structured log records → formula-phase findings.

    Only assertion-result records (``message:v…``) become findings. Deactivated
    rules are dropped. Duplicate rule ids (same rule firing per-fact) collapse to
    one finding per rule id, keeping the first location.
    """
    findings: list[Finding] = []
    seen: set[str] = set()
    for record in records:
        m = _ASSERTION_CODE.match(str(record.get("code", "")))
        if m is None:
            continue
        rule_id = m.group(1)
        if rule_id in deactivated_rules or rule_id in seen:
            continue
        seen.add(rule_id)
        text = _message_text(record)
        findings.append(
            Finding(
                severity=_LEVEL_TO_SEVERITY.get(
                    record.get("level", "warning"), Severity.warning
                ),
                phase=ValidationPhase.formula,
                code=rule_id,
                message=text or f"assertion {rule_id} not satisfied",
                file="formula",
                **_parse_location(text),
            )
        )
    return findings


class FormulaValidator(Protocol):
    """Interface so the runtime can swap Arelle for a stub / null implementation."""

    def validate(
        self, package_path: Path, taxonomy_packages: list[Path]
    ) -> list[Finding]: ...


def unavailable_finding(reason: str) -> Finding:
    """A non-blocking finding when formula validation could not run."""
    return Finding(
        severity=Severity.info,
        phase=ValidationPhase.formula,
        code="FORMULA_VALIDATION_UNAVAILABLE",
        message=f"formula validation unavailable: {reason}",
    )


def eurofiling_package(cache_dir: Path) -> Path:
    """Build (once, cached) the vendored eurofiling files into a taxonomy package
    zip Arelle can load. Returns the zip path."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / "eurofiling-core.zip"
    if out.exists():
        return out
    root = "eurofiling-core"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(_VENDOR_EUROFILING.rglob("*")):
            if path.is_file() and path.name != "README.md":
                zf.write(path, f"{root}/{path.relative_to(_VENDOR_EUROFILING)}")
    return out


class ArelleFormulaValidator:
    """Runs Arelle offline with ``--formula run`` and maps the results.

    ``cache_dir`` holds the built eurofiling package. A crash (Arelle missing or
    an internal error) is turned into a single non-blocking finding — the caller
    must never let this fail a run.
    """

    def __init__(
        self, *, cache_dir: Path, deactivated_rules: set[str] | None = None
    ) -> None:
        self._cache_dir = cache_dir
        self._deactivated = load_deactivated_rules(deactivated_rules)

    def validate(
        self, package_path: Path, taxonomy_packages: list[Path]
    ) -> list[Finding]:
        if not taxonomy_packages:
            return [unavailable_finding("no taxonomy package for this snapshot")]
        try:
            records = self._run_arelle(package_path, taxonomy_packages)
        except ImportError as exc:
            return [unavailable_finding(f"Arelle not installed ({exc})")]
        except Exception as exc:  # noqa: BLE001 — never crash a run
            logger.exception("Arelle formula validation errored")
            return [unavailable_finding(f"Arelle error: {exc}")]

        # A load failure means "0 assertions" is not a clean pass — surface it
        # (a version mismatch between the package and the taxonomy is the usual
        # cause) rather than silently reporting no findings.
        load_errors = [
            r
            for r in records
            if r.get("level") == "error" and r.get("code") in _LOAD_ERROR_CODES
        ]
        if load_errors:
            return [
                unavailable_finding(
                    "taxonomy/package failed to load "
                    f"({load_errors[0].get('code')}); check the taxonomy package "
                    "matches the package's declared version"
                )
            ]
        return findings_from_arelle_records(
            records, deactivated_rules=self._deactivated
        )

    def _run_arelle(
        self, package_path: Path, taxonomy_packages: list[Path]
    ) -> list[dict]:
        from arelle import CntlrCmdLine  # lazy: optional dependency

        args: list[str] = [
            "--file", str(package_path),
            "--reportPackage",
            "--validate",
            "--formula", "run",
            "--internetConnectivity", "offline",
            "--logFile", "logToBuffer",
        ]
        for pkg in [*taxonomy_packages, eurofiling_package(self._cache_dir)]:
            args += ["--packages", str(pkg)]
        cntlr = CntlrCmdLine.parseAndRun(args)
        try:
            data = json.loads(cntlr.logHandler.getJson())
            return data.get("log", [])
        finally:
            cntlr.close()
