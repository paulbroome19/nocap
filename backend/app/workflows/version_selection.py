"""Taxonomy version selection + ingestion summary.

Reads the modules each release records at ingest (``release_module``) and turns
them into the user-facing surfaces:

- ``list_module_versions`` — the version dropdown for a reporting suite: the
  distinct ``(module_version, framework_version)`` a module is available at
  across all ready releases, collapsing identical keys and presenting distinct
  ones. Which releases provide a version is supporting detail, not a choice.
- ``release_provisions_summary`` — what a freshly ingested release provides for
  each enabled suite, and whether it is new to the estate.

Lives in ``workflows`` because it joins the taxonomy record to the reporting
suites (``WorkflowConfig``); it reads taxonomy models but writes nothing.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.taxonomy.models import (
    ReleaseModule,
    SnapshotStatus,
    TaxonomySnapshot,
)
from app.workflows.models import WorkflowConfig
from app.workflows.schemas import (
    ModuleVersionOption,
    ModuleVersionOptions,
    ReleaseProvision,
    ReleaseProvisionsSummary,
)


def _version_key(v: str) -> tuple:
    """Sort key so "3.10.0" sorts after "3.3.0" (numeric, not lexical)."""
    parts = []
    for p in v.split("."):
        parts.append((0, int(p)) if p.isdigit() else (1, p))
    return tuple(parts)


def _ready_snapshots(db: Session) -> dict[int, TaxonomySnapshot]:
    """Ready releases by id — the only ones a run may bind to."""
    rows = db.scalars(
        select(TaxonomySnapshot).where(
            TaxonomySnapshot.status == SnapshotStatus.ready
        )
    )
    return {s.id: s for s in rows}


def list_module_versions(
    db: Session, workflow_id: int
) -> ModuleVersionOptions:
    """The distinct taxonomy versions a suite's module is available at, across
    all ready releases. Empty when no ready release contains the module."""
    wf = db.get(WorkflowConfig, workflow_id)
    if wf is None:
        from app.core.errors import NotFoundError

        raise NotFoundError(f"workflow id={workflow_id} not found")

    ready = _ready_snapshots(db)
    rows = db.scalars(
        select(ReleaseModule).where(ReleaseModule.module_code == wf.module_code)
    )

    # group distinct (module_version, framework_version) → the release_module
    # rows providing it (only from ready releases).
    groups: dict[tuple[str, str], list[ReleaseModule]] = {}
    for rm in rows:
        if rm.snapshot_id not in ready:
            continue
        groups.setdefault((rm.module_version, rm.framework_version), []).append(rm)

    options: list[ModuleVersionOption] = []
    for (module_version, framework_version), rms in groups.items():
        # newest release providing it first (highest snapshot id)
        rms_sorted = sorted(rms, key=lambda r: r.snapshot_id, reverse=True)
        newest = rms_sorted[0]
        options.append(
            ModuleVersionOption(
                module_code=wf.module_code,
                module_name=newest.module_name,
                module_version=module_version,
                framework_version=framework_version,
                snapshot_id=newest.snapshot_id,  # the release a run binds to
                valid_from=newest.valid_from,
                valid_to=newest.valid_to,
                provided_by=[ready[r.snapshot_id].display_name for r in rms_sorted],
            )
        )

    # newest module version first; nothing is preselected (the UI chooses none).
    options.sort(key=lambda o: _version_key(o.module_version), reverse=True)
    return ModuleVersionOptions(
        workflow_id=workflow_id, module_code=wf.module_code, options=options
    )


def release_provisions_summary(
    db: Session, snapshot_id: int
) -> ReleaseProvisionsSummary:
    """For each enabled reporting suite, what this release provides and whether
    it is new — the "what did this update change in our estate" answer."""
    active = list(
        db.scalars(
            select(WorkflowConfig)
            .where(WorkflowConfig.is_active.is_(True))
            .order_by(WorkflowConfig.name)
        )
    )
    ready = _ready_snapshots(db)

    provisions: list[ReleaseProvision] = []
    for wf in active:
        this = db.scalar(
            select(ReleaseModule).where(
                ReleaseModule.snapshot_id == snapshot_id,
                ReleaseModule.module_code == wf.module_code,
            )
        )
        if this is None:
            # This release does not contain the suite's module.
            provisions.append(
                ReleaseProvision(
                    module_code=wf.module_code,
                    module_name=None,
                    workflow_name=wf.name,
                    module_version=None,
                    framework_version=None,
                    is_new=False,
                    already_from=None,
                )
            )
            continue

        # Earlier ready releases providing the same version → not new; name the
        # earliest (the release this version first became available from).
        earlier = [
            ready[rm.snapshot_id]
            for rm in db.scalars(
                select(ReleaseModule).where(
                    ReleaseModule.module_code == wf.module_code,
                    ReleaseModule.module_version == this.module_version,
                    ReleaseModule.framework_version == this.framework_version,
                    ReleaseModule.snapshot_id != snapshot_id,
                )
            )
            if rm.snapshot_id in ready and rm.snapshot_id < snapshot_id
        ]
        earliest = min(earlier, key=lambda s: s.id) if earlier else None
        provisions.append(
            ReleaseProvision(
                module_code=wf.module_code,
                module_name=this.module_name,
                workflow_name=wf.name,
                module_version=this.module_version,
                framework_version=this.framework_version,
                is_new=earliest is None,
                already_from=earliest.display_name if earliest else None,
            )
        )

    return ReleaseProvisionsSummary(snapshot_id=snapshot_id, provisions=provisions)
