"""Release coherence — cross-check artifact versions, warn on mismatch.

A release's three functional artifacts are published together at one framework
version. When they don't agree — a 4.1 taxonomy package dropped onto a 4.2 DPM,
a workbook for the wrong release — the mismatch used to surface only downstream
as a cryptic Arelle load error. This computes the versions each artifact
declares (where extractable) and returns human warnings for any disagreement.

Warnings, never blocks: the release stays usable; the run just carries the
caveat. Computed on read from the current artifact states.

Per the dependency rules this imports only ``app.core`` and its own stage.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.taxonomy import service as taxonomy
from app.taxonomy.models import (
    ArtifactStatus,
    ReleaseArtifact,
    ReleaseSlot,
    TaxonomySnapshot,
    ValidationRule,
)

logger = logging.getLogger(__name__)

# A full dotted version: "4.2", "4.2.1", "4.2.0.0". At least two components so a
# bare year/count isn't mistaken for a version.
_VERSION_TOKEN = re.compile(r"\d+(?:\.\d+)+")
# The framework version inside a module token, e.g. "4.2.1" in "COREP_LCR_DA_4.2.1".
_MODULE_VERSION = re.compile(r"_(\d+(?:\.\d+)+)")


def _parse_version(text: str | None) -> str | None:
    """The most specific dotted version in ``text`` (the one with the most
    components), or ``None``.

    Crucially this keeps the *full* version — "4.2.1", not "4.2". The old code
    truncated to major.minor, so a 4.2.1 DPM and a 4.2 taxonomy package compared
    equal and no mismatch was reported.
    """
    if not text:
        return None
    tokens = _VERSION_TOKEN.findall(text)
    if not tokens:
        return None
    return max(tokens, key=lambda t: t.count("."))


def _version_sort_key(v: str) -> tuple[int, ...]:
    """Numeric sort key so "4.10" sorts after "4.2" (not lexicographically)."""
    return tuple(int(p) for p in v.split("."))


def _versions_agree(a: str, b: str) -> bool:
    """Whether two dotted versions denote the same framework release.

    Compared component-by-component with missing trailing components treated as
    zero, so "4.2" agrees with "4.2.0.0" but **not** with "4.2.1". This is what
    distinguishes a 4.2 taxonomy package from a 4.2.1 DPM — the patch-level
    mismatch the old major.minor-only check silently accepted.
    """
    pa = [int(p) for p in a.split(".")]
    pb = [int(p) for p in b.split(".")]
    width = max(len(pa), len(pb))
    pa += [0] * (width - len(pa))
    pb += [0] * (width - len(pb))
    return pa == pb


def _dpm_version(
    db: Session, snapshot: TaxonomySnapshot, settings: Settings
) -> str | None:
    """The DPM's framework version — the release code if readable, else the label.

    The release code is authoritative and carries the patch level (e.g. the
    current release of a DPM 4.2.1 file is ``4.2.1``), so prefer it over the
    user-typed label (which may say just "4.2").
    """
    try:
        with taxonomy.open_lookup(snapshot, settings=settings) as lk:
            code = lk.release_code(lk.default_release_id())
            version = _parse_version(code)
            if version:
                return version
    except Exception:  # noqa: BLE001 — lookup optional; fall back to the label
        pass
    return _parse_version(snapshot.version_label)


def _taxonomy_version(db: Session, snapshot_id: int) -> str | None:
    """Version extractable from the taxonomy package filename, if any."""
    artifact = db.scalar(
        select(ReleaseArtifact).where(
            ReleaseArtifact.snapshot_id == snapshot_id,
            ReleaseArtifact.slot == ReleaseSlot.taxonomy_package,
            ReleaseArtifact.status == ArtifactStatus.ready,
        )
    )
    return _parse_version(artifact.filename) if artifact else None


def _workbook_versions(db: Session, snapshot_id: int) -> set[str]:
    """Framework versions carried by the ingested workbook's module tokens."""
    versions: set[str] = set()
    for modules in db.scalars(
        select(ValidationRule.modules).where(
            ValidationRule.snapshot_id == snapshot_id
        )
    ):
        versions.update(_MODULE_VERSION.findall(modules or ""))
    return versions


def coherence_warnings(
    db: Session,
    snapshot: TaxonomySnapshot,
    *,
    settings: Settings | None = None,
) -> list[str]:
    """Version-mismatch warnings across the release's functional artifacts."""
    settings = settings or get_settings()
    dpm = _dpm_version(db, snapshot, settings)
    if dpm is None:
        return []  # nothing to compare against

    warnings: list[str] = []

    taxo = _taxonomy_version(db, snapshot.id)
    if taxo is not None and not _versions_agree(taxo, dpm):
        warnings.append(
            f"The taxonomy package (version {taxo}) does not match the DPM "
            f"database (version {dpm}). Upload the taxonomy package published "
            f"for DPM {dpm}, or the DPM for taxonomy {taxo}."
        )

    # The rules workbook is legitimately multi-version — a single workbook carries
    # rules for modules across several framework releases. So it is coherent as
    # long as it *includes* the DPM's version; only warn if none of its versions
    # match (e.g. a 4.1-only workbook on a 4.2.1 DPM).
    wb_versions = _workbook_versions(db, snapshot.id)
    if wb_versions and not any(_versions_agree(v, dpm) for v in wb_versions):
        listed = ", ".join(sorted(wb_versions, key=_version_sort_key))
        warnings.append(
            f"The validation-rules workbook (versions {listed}) does not include "
            f"the DPM database's version ({dpm}). Upload the validation rules "
            f"published for DPM {dpm}."
        )
    return warnings
