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

# A framework version like "4.2"; also the trailing "_4.2" in a module token.
_VERSION = re.compile(r"(\d+\.\d+)")
_MODULE_VERSION = re.compile(r"_(\d+\.\d+)\b")


def _first_version(text: str | None) -> str | None:
    if not text:
        return None
    m = _VERSION.search(text)
    return m.group(1) if m else None


def _dpm_version(
    db: Session, snapshot: TaxonomySnapshot, settings: Settings
) -> str | None:
    """The DPM's framework version — the release code if readable, else the label."""
    try:
        with taxonomy.open_lookup(snapshot, settings=settings) as lk:
            code = lk.release_code(lk.default_release_id())
            if _first_version(code):
                return _first_version(code)
    except Exception:  # noqa: BLE001 — lookup optional; fall back to the label
        pass
    return _first_version(snapshot.version_label)


def _taxonomy_version(db: Session, snapshot_id: int) -> str | None:
    """Version extractable from the taxonomy package filename, if any."""
    artifact = db.scalar(
        select(ReleaseArtifact).where(
            ReleaseArtifact.snapshot_id == snapshot_id,
            ReleaseArtifact.slot == ReleaseSlot.taxonomy_package,
            ReleaseArtifact.status == ArtifactStatus.ready,
        )
    )
    return _first_version(artifact.filename) if artifact else None


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
    if taxo is not None and taxo != dpm:
        warnings.append(
            f"taxonomy package {taxo} does not match DPM {dpm}"
        )

    wb_versions = _workbook_versions(db, snapshot.id)
    if wb_versions and dpm not in wb_versions:
        listed = ", ".join(sorted(wb_versions))
        warnings.append(
            f"validation-rules workbook {listed} does not match DPM {dpm}"
        )
    return warnings
