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
from app.taxonomy import artifacts, capabilities, rules, service
from app.taxonomy.models import ReleaseSlot, TaxonomySnapshot
from app.taxonomy.schemas import (
    CapabilitySetOut,
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
    ]
    caps = capabilities.derive_capabilities(slot_views)
    return ReleaseDetailOut(
        release=SnapshotOut.model_validate(snapshot),
        ready=artifacts.release_ready(snapshot),
        slots=slots,
        capabilities=CapabilitySetOut(**caps.to_dict()),
        coherence_warnings=[],  # populated by the coherence check (next checkpoint)
    )


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


@router.post("/snapshots", response_model=SnapshotOut, status_code=202)
async def upload_snapshot(
    background: BackgroundTasks,
    version_label: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> SnapshotOut:
    """Accept a DPM release, register it, and start ingestion in the background."""
    data = await file.read()
    snapshot = service.register_snapshot(
        db,
        file_bytes=data,
        filename=file.filename or "upload.accdb",
        version_label=version_label,
    )
    background.add_task(service.ingest_snapshot_task, snapshot.id)
    return SnapshotOut.model_validate(snapshot)
