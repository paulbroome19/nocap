"""Empirical coherence gate for release creation.

The last step of creating a release is to prove the taxonomy package actually
resolves the DPM's current-release entry point in Arelle — rather than trusting
that version *strings* agree. A 4.2 taxonomy package on a 4.2.1 DPM parses fine
and its filename says "4.2", but Arelle cannot resolve the 4.2.1 entry point it
would be asked to load, so a real submission fails downstream with
``xbrlce:unresolvableBaseMetadataFile``. This runs that load here, at creation,
so the mismatch fails creation transactionally (nothing left behind) with a
plain-language reason.

Lives in ``workflows`` because it is the only layer allowed to combine the three
stages it needs: the DPM lookup (taxonomy), the entry-point URL + a minimal
report package (generation), and the Arelle load (validation). It is injected
into ``taxonomy.service`` at startup (see app.main), which must not import them.
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.core.db import SessionLocal
from app.core.errors import ValidationError
from app.generation import service as generation
from app.generation.schemas import PackageMetadata
from app.taxonomy import service as taxonomy
from app.taxonomy.service import TaxonomyLookup
from app.validation import arelle_adapter
from app.workflows.models import WorkflowConfig

logger = logging.getLogger(__name__)


def _entry_point_metadata(
    lk: TaxonomyLookup, release_code: str, release_id: int
) -> PackageMetadata | None:
    """Minimal package metadata for a module present in the DPM's current
    release — enough to build a report that ``extends`` that module's entry
    point. Picks the first active reporting suite whose module is in the release
    (that is the entry point a real run would load), or ``None`` if there is no
    usable module to test.
    """
    with SessionLocal() as db:
        configs = list(
            db.scalars(
                select(WorkflowConfig).where(WorkflowConfig.is_active.is_(True))
            )
        )
    for wf in configs:
        meta = lk.module_metadata(wf.module_code, release_id=release_id)
        if meta is None:
            continue
        return PackageMetadata(
            entity_lei="00000000000000000000",
            scope="CON",
            country="XX",
            reference_date=date(2020, 1, 1),
            creation_timestamp="20200101000000000",
            framework_code=meta.framework_code,
            module_code=meta.module_code,
            module_version=meta.module_version,
            taxonomy_version=release_code,  # the URL segment a real run uses
            base_currency="EUR",
            decimals=-3,
            filing_indicators=[],
        )
    return None


def verify_release_taxonomy_loads(
    snapshot_id: int, settings: Settings | None = None
) -> None:
    """Load-test the taxonomy package against the DPM's current-release entry
    point. Raises ``ValidationError`` (a plain-language reason) if it does not
    resolve; returns silently when it loads, when Arelle is disabled, or when
    there is nothing to test.
    """
    settings = settings or get_settings()
    if not settings.arelle_enabled:
        return

    packages = taxonomy.snapshot_taxonomy_packages(settings, snapshot_id)
    if not packages:
        return  # no taxonomy package to test (creation requires one, so rare)

    sqlite_path = taxonomy._sqlite_path(settings, snapshot_id)
    if not sqlite_path.exists():
        return

    with TaxonomyLookup(sqlite_path) as lk:
        release_id = lk.default_release_id()
        release_code = lk.release_code(release_id) or ""
        metadata = _entry_point_metadata(lk, release_code, release_id)
    if metadata is None:
        return

    # A minimal (zero-fact) report package that extends the module's entry point.
    package = generation.build_package(
        [], metadata, resolve=lambda *_: None, strict=False
    )
    cache = settings.data_dir / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    probe = cache / f"coherence-probe-{snapshot_id}.zip"
    probe.write_bytes(package.content)
    try:
        errors = arelle_adapter.taxonomy_load_errors(
            probe, packages, cache_dir=cache
        )
    finally:
        probe.unlink(missing_ok=True)

    if errors:
        code = errors[0].get("code", "load error")
        entry = generation.entry_point_url(metadata)
        logger.warning(
            "release load gate failed for snapshot id=%s: %s (%s)",
            snapshot_id, code, entry,
        )
        raise ValidationError(
            "The taxonomy package does not match the DPM database. The DPM's "
            f"current release is {release_code}, but the taxonomy package could "
            f"not resolve that release's entry point ({code}). Upload the "
            f"taxonomy package published for DPM {release_code} (or the DPM for "
            "the taxonomy package you uploaded)."
        )
    logger.info(
        "release load gate passed for snapshot id=%s (DPM %s)",
        snapshot_id, release_code,
    )
