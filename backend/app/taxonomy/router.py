"""HTTP routes for the taxonomy stage — thin: parse, call service, shape response.

Snapshot registry + DPM upload. Ingestion (Access -> SQLite conversion) runs as
a background task; clients poll the snapshot detail for status.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.taxonomy import artifacts, capabilities, coherence, rules, service
from app.taxonomy.models import ReleaseSlot, TaxonomySnapshot
from app.taxonomy.schemas import (
    CapabilitySetOut,
    RegulatorOut,
    ReleaseDetailOut,
    ReleaseSlotOut,
    SnapshotOut,
)

router = APIRouter()


def _snapshot_out(db: Session, snapshot: TaxonomySnapshot) -> SnapshotOut:
    """A snapshot with its derived capabilities attached."""
    out = SnapshotOut.model_validate(snapshot)
    caps = capabilities.derive_capabilities(artifacts.list_slots(db, snapshot))
    out.capabilities = CapabilitySetOut(**caps.to_dict())
    return out


def _release_detail(db: Session, snapshot: TaxonomySnapshot) -> ReleaseDetailOut:
    slot_views = artifacts.list_slots(db, snapshot)
    # The three functional artifacts only. Reference slots (filing rules,
    # samples) are kept in the repo docs but are not part of the release surface.
    slots = [
        ReleaseSlotOut(
            slot=v.spec.slot,
            label=v.spec.label,
            requirement=v.spec.requirement,
            accept=list(v.spec.accept),
            description=v.spec.description,
            status=v.status,
            filename=v.filename,
            checksum=v.checksum,
            error=v.error,
            uploaded_at=v.uploaded_at,
        )
        for v in slot_views
        if v.spec.requirement != "reference"
    ]
    caps = capabilities.derive_capabilities(slot_views)
    return ReleaseDetailOut(
        release=SnapshotOut.model_validate(snapshot),
        ready=artifacts.release_ready(snapshot),
        slots=slots,
        capabilities=CapabilitySetOut(**caps.to_dict()),
        coherence_warnings=coherence.coherence_warnings(db, snapshot),
    )


@router.get("/regulators", response_model=list[RegulatorOut])
def list_regulators(db: Session = Depends(get_db)) -> list[RegulatorOut]:
    """The taxonomy publishers (e.g. EBA) — the top of the Taxonomies section."""
    return [RegulatorOut.model_validate(r) for r in service.list_regulators(db)]


@router.get("/regulators/{regulator_id}", response_model=RegulatorOut)
def get_regulator(
    regulator_id: int, db: Session = Depends(get_db)
) -> RegulatorOut:
    return RegulatorOut.model_validate(service.get_regulator(db, regulator_id))


@router.get(
    "/regulators/{regulator_id}/releases", response_model=list[SnapshotOut]
)
def list_regulator_releases(
    regulator_id: int, db: Session = Depends(get_db)
) -> list[SnapshotOut]:
    """The releases published by one regulator."""
    service.get_regulator(db, regulator_id)  # 404 if unknown
    service.verify_all_snapshots(db)
    return [
        _snapshot_out(db, s)
        for s in service.list_snapshots_for_regulator(db, regulator_id)
    ]


@router.get("/snapshots", response_model=list[SnapshotOut])
def list_snapshots(db: Session = Depends(get_db)) -> list[SnapshotOut]:
    # Reconcile status with what's on disk so the registry never shows "ready"
    # for a snapshot whose artifacts have gone missing.
    service.verify_all_snapshots(db)
    return [_snapshot_out(db, s) for s in service.list_snapshots(db)]


@router.get("/snapshots/{snapshot_id}", response_model=SnapshotOut)
def get_snapshot(snapshot_id: int, db: Session = Depends(get_db)) -> SnapshotOut:
    snapshot = service.get_snapshot(db, snapshot_id)
    service.verify_snapshot(db, snapshot)
    return _snapshot_out(db, snapshot)


@router.post("/snapshots/{snapshot_id}/reingest", response_model=SnapshotOut)
def reingest_snapshot(
    snapshot_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> SnapshotOut:
    """Rebuild the converted DB from the stored original (no re-upload)."""
    snapshot = service.reingest_snapshot(db, snapshot_id)
    background.add_task(service.ingest_snapshot_task, snapshot.id)
    return SnapshotOut.model_validate(snapshot)


@router.get("/snapshots/{snapshot_id}/artifacts", response_model=ReleaseDetailOut)
def release_artifacts(
    snapshot_id: int, db: Session = Depends(get_db)
) -> ReleaseDetailOut:
    """The release's typed artifact slots + readiness (release detail view)."""
    snapshot = service.get_snapshot(db, snapshot_id)
    service.verify_snapshot(db, snapshot)
    return _release_detail(db, snapshot)


@router.post(
    "/snapshots/{snapshot_id}/artifacts/{slot}", response_model=ReleaseDetailOut
)
async def upload_release_artifact(
    snapshot_id: int,
    slot: str,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ReleaseDetailOut:
    """Upload a file into a slot (taxonomy package / validation rules / …).

    The validation-rules workbook is header-verified here then ingested in the
    background (its slot shows ``verifying`` until done); other slots are stored
    with a synchronous light check.
    """
    snapshot = service.get_snapshot(db, snapshot_id)
    parsed = artifacts.parse_slot(slot)
    data = await file.read()
    if parsed is ReleaseSlot.validation_rules:
        rules.store_workbook(
            db, snapshot, filename=file.filename or "rules.xlsx", data=data
        )
        background.add_task(rules.ingest_validation_rules_task, snapshot.id)
    else:
        artifacts.store_artifact(
            db, snapshot, parsed, filename=file.filename or "upload", data=data
        )
    db.refresh(snapshot)
    return _release_detail(db, snapshot)


@router.get("/artifacts/{artifact_id}/download")
def download_artifact(
    artifact_id: int, db: Session = Depends(get_db)
) -> FileResponse:
    artifact = artifacts.get_artifact(db, artifact_id)
    path = get_settings().data_dir / artifact.storage_key
    return FileResponse(
        path, filename=artifact.filename, media_type="application/octet-stream"
    )


@router.post("/releases", response_model=SnapshotOut, status_code=201)
async def create_release(
    version_label: str = Form(...),
    regulator_id: int = Form(...),
    dpm_file: UploadFile = File(...),
    taxonomy_file: UploadFile = File(...),
    rules_file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> SnapshotOut:
    """Create a release from its three mandatory artifacts — all or nothing.

    Verification, DPM conversion, and rule ingestion all complete before the
    release exists; a failure at any stage creates no release and leaves no files
    (HTTP 422 with a plain-language reason). On success the release is returned
    ``ready`` — a listed release is always usable.
    """
    snapshot = service.create_release(
        db,
        regulator_id=regulator_id,
        version_label=version_label,
        dpm_bytes=await dpm_file.read(),
        dpm_filename=dpm_file.filename or "dpm.accdb",
        taxonomy_bytes=await taxonomy_file.read(),
        taxonomy_filename=taxonomy_file.filename or "taxonomy.zip",
        rules_bytes=await rules_file.read(),
        rules_filename=rules_file.filename or "rules.xlsx",
    )
    return _snapshot_out(db, snapshot)


@router.delete("/snapshots/{snapshot_id}", status_code=204)
def delete_release(snapshot_id: int, db: Session = Depends(get_db)) -> None:
    """Delete a release and everything derived from it.

    Allowed regardless of any runs produced from it — historical runs are frozen
    and keep their own copies, so deletion never alters them.
    """
    snapshot = service.get_snapshot(db, snapshot_id)
    service.delete_release(db, snapshot)
