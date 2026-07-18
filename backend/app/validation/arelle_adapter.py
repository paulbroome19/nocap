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
from dataclasses import dataclass, field
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
# Per-assertion result-count trace (from --formulaSatisfiedAsser/UnsatisfiedAsser):
#   "Value Assertion v7681_s_15 evaluations : 0 satisfied, 0 not satisfied - <url>"
_ASSERTION_TRACE = re.compile(
    r"(Value|Existence|Consistency) Assertion (v\d+_[a-z]+)(?:_\d+)? "
    r"evaluations : (\d+) satisfied, (\d+) not satisfied"
)
# The evaluated comparison in an unsatisfied message, e.g.
#   "... >= ... Fails because 57621 >= 66241 is not true."
_FAILS_BECAUSE = re.compile(r"Fails? because (.+?) is not true", re.DOTALL)
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
    rules are dropped. A rule firing on several facts collapses to one finding.

    **Deterministic**: Arelle emits per-fact assertion messages in a
    non-deterministic order, so we group all messages per rule id and pick the
    lexicographically-smallest text (and sort by rule id) rather than keeping
    "the first seen". Otherwise the same run yields different findings each time,
    independent of any model caching.
    """
    by_rule: dict[str, list[tuple[str, str]]] = {}
    for record in records:
        m = _ASSERTION_CODE.match(str(record.get("code", "")))
        if m is None:
            continue
        rule_id = m.group(1)
        if rule_id in deactivated_rules:
            continue
        by_rule.setdefault(rule_id, []).append(
            (str(record.get("level", "warning")), _message_text(record))
        )

    findings: list[Finding] = []
    for rule_id in sorted(by_rule):
        level, text = min(by_rule[rule_id], key=lambda e: e[1])
        findings.append(
            Finding(
                severity=_LEVEL_TO_SEVERITY.get(level, Severity.warning),
                phase=ValidationPhase.formula,
                code=rule_id,
                message=text or f"assertion {rule_id} not satisfied",
                file="formula",
                **_parse_location(text),
            )
        )
    return findings


@dataclass
class RuleResult:
    """A single formula rule's evaluated result (for the rule register)."""

    rule_id: str
    assertion_type: str  # "Value Assertion" | "Existence Assertion" | ...
    satisfied: int
    not_satisfied: int
    result: str  # "PASSED" | "FAILED"
    values: str | None  # extracted "A >= B" comparison (unsatisfied only)
    message: str | None  # full unsatisfied message, when present


@dataclass
class FormulaRun:
    """Full result of a formula-validation run.

    ``available`` is False when the taxonomy/package failed to load (so 0
    assertions is not a clean pass). ``rule_results`` holds only the rules that
    actually *evaluated* (satisfied + not_satisfied > 0); ``loaded`` counts all
    assertions Arelle traced (evaluated or not).
    """

    findings: list[Finding]
    rule_results: list[RuleResult]
    available: bool
    unavailable_reason: str | None = None
    loaded: int = 0
    deactivated: list[str] = field(default_factory=list)
    # Count of facts Arelle rejected as unknown property groups — must be 0 for a
    # correctly-generated package (see the dp{VariableID} fix + the CI guard).
    unknown_property_groups: int = 0


def rule_results_from_records(
    records: list[dict], *, deactivated_rules: set[str]
) -> tuple[list[RuleResult], int]:
    """Per-rule results from Arelle's assertion traces + unsatisfied messages.

    Returns ``(evaluated_rules, loaded_count)``. Trace records give
    satisfied/not-satisfied counts per rule (aggregated over evaluation
    instances); unsatisfied ``message:`` records supply the evaluated comparison
    for failed rules. Deactivated rules are dropped. Only rules that evaluated
    (counts > 0) are returned as results; ``loaded`` counts every rule traced.
    """
    # rule_id -> [satisfied, not_satisfied, assertion_type]
    counts: dict[str, list] = {}
    for record in records:
        m = _ASSERTION_TRACE.search(_message_text(record))
        if m is None:
            continue
        atype, rule_id, sat, notsat = m.groups()
        if rule_id in deactivated_rules:
            continue
        agg = counts.setdefault(rule_id, [0, 0, atype])
        agg[0] += int(sat)
        agg[1] += int(notsat)

    # Unsatisfied messages (evaluated values) per rule id. Deterministic: keep
    # the lexicographically-smallest message, not the first-seen (Arelle's
    # per-fact message order is non-deterministic).
    messages: dict[str, str] = {}
    for record in records:
        m = _ASSERTION_CODE.match(str(record.get("code", "")))
        if m is None:
            continue
        rule_id = m.group(1)
        if rule_id in deactivated_rules:
            continue
        text = _message_text(record)
        if rule_id not in messages or text < messages[rule_id]:
            messages[rule_id] = text

    results: list[RuleResult] = []
    for rule_id, (sat, notsat, atype) in counts.items():
        if sat + notsat == 0:
            continue  # loaded but not evaluated against this submission's data
        msg = messages.get(rule_id)
        values = None
        if msg:
            fm = _FAILS_BECAUSE.search(msg)
            values = fm.group(1).strip() if fm else None
        results.append(
            RuleResult(
                rule_id=rule_id,
                assertion_type=atype,
                satisfied=sat,
                not_satisfied=notsat,
                result="FAILED" if notsat > 0 else "PASSED",
                values=values,
                message=msg,
            )
        )
    results.sort(key=lambda r: (r.result != "FAILED", r.rule_id))
    return results, len(counts)


def expand_taxonomy_packages(
    packages: list[Path], cache_dir: Path
) -> list[Path]:
    """Expand EBA *container* zips into the inner taxonomy packages Arelle loads.

    The EBA 4.2 release ships as a container zip holding the Dictionary /
    Reporting Frameworks / Severity taxonomy packages (plus release notes) — it
    is not itself a taxonomy package (no root ``META-INF/taxonomyPackage.xml``).
    Passing the container to ``--packages`` fails with ``invalidDirectory
    structure``; the inner zips must be extracted and passed instead. A zip that
    already *is* a taxonomy package is returned unchanged.
    """
    expanded_dir = cache_dir / "expanded"
    out: list[Path] = []
    for container in packages:
        try:
            with zipfile.ZipFile(container) as zf:
                names = zf.namelist()
                if any(n == "META-INF/taxonomyPackage.xml" for n in names):
                    out.append(container)
                    continue
                inner = [n for n in names if n.lower().endswith(".zip")]
                if not inner:
                    out.append(container)  # not a container; let Arelle judge it
                    continue
                expanded_dir.mkdir(parents=True, exist_ok=True)
                for name in inner:
                    dest = expanded_dir / Path(name).name
                    if not dest.exists():
                        dest.write_bytes(zf.read(name))
                    out.append(dest)
        except zipfile.BadZipFile:
            out.append(container)
    return out


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
        """Findings-only entry point (backward compatible)."""
        return self.validate_detailed(package_path, taxonomy_packages).findings

    def validate_detailed(
        self, package_path: Path, taxonomy_packages: list[Path]
    ) -> FormulaRun:
        """Run Arelle and return findings + per-rule results for the register."""
        deactivated = sorted(self._deactivated)
        if not taxonomy_packages:
            reason = "no taxonomy package for this snapshot"
            return FormulaRun(
                [unavailable_finding(reason)], [], False, reason,
                deactivated=deactivated,
            )
        try:
            records = self._run_arelle(package_path, taxonomy_packages)
        except ImportError as exc:
            reason = f"Arelle not installed ({exc})"
            return FormulaRun(
                [unavailable_finding(reason)], [], False, reason,
                deactivated=deactivated,
            )
        except Exception as exc:  # noqa: BLE001 — never crash a run
            logger.exception("Arelle formula validation errored")
            reason = f"Arelle error: {exc}"
            return FormulaRun(
                [unavailable_finding(reason)], [], False, reason,
                deactivated=deactivated,
            )

        # A load failure means "0 assertions" is not a clean pass — surface it
        # (a version mismatch between the package and the taxonomy is the usual
        # cause) rather than silently reporting no findings.
        load_errors = [
            r
            for r in records
            if r.get("level") == "error" and r.get("code") in _LOAD_ERROR_CODES
        ]
        if load_errors:
            reason = (
                "taxonomy/package failed to load "
                f"({load_errors[0].get('code')}); check the taxonomy package "
                "matches the package's declared version"
            )
            return FormulaRun(
                [unavailable_finding(reason)], [], False, reason,
                deactivated=deactivated,
            )

        findings = findings_from_arelle_records(
            records, deactivated_rules=self._deactivated
        )
        rule_results, loaded = rule_results_from_records(
            records, deactivated_rules=self._deactivated
        )
        unknown_pg = sum(
            1 for r in records if r.get("code") == "xbrlce:unknownPropertyGroup"
        )
        return FormulaRun(
            findings=findings,
            rule_results=rule_results,
            available=True,
            loaded=loaded,
            deactivated=deactivated,
            unknown_property_groups=unknown_pg,
        )

    def _arelle_args(
        self, package_path: Path, packages: list[Path]
    ) -> list[str]:
        args: list[str] = [
            "--file", str(package_path),
            "--reportPackage",
            "--validate",
            "--formula", "run",
            # Log per-assertion result counts ("N satisfied, M not satisfied")
            # so we can build the rule register (satisfied + not just failures),
            # not only the unsatisfied-assertion messages.
            "--formulaAsserResultCounts",
            "--internetConnectivity", "offline",
            "--logFile", "logToBuffer",
        ]
        for pkg in [*packages, eurofiling_package(self._cache_dir)]:
            args += ["--packages", str(pkg)]
        return args

    def _run_arelle(
        self, package_path: Path, taxonomy_packages: list[Path]
    ) -> list[dict]:
        # A fresh controller per run: reusing a warm controller neither speeds
        # anything up (Arelle re-parses the DTS every load) nor preserves
        # findings identity (see docs/formula-cache-findings.md).
        from arelle import CntlrCmdLine  # lazy: optional dependency

        packages = expand_taxonomy_packages(taxonomy_packages, self._cache_dir)
        cntlr = CntlrCmdLine.parseAndRun(self._arelle_args(package_path, packages))
        try:
            data = json.loads(cntlr.logHandler.getJson())
            return data.get("log", [])
        finally:
            cntlr.close()
