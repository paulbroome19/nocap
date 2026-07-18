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
from app.taxonomy import artifacts, service
from app.taxonomy.models import TaxonomySnapshot
from app.taxonomy.schemas import ReleaseDetailOut, ReleaseSlotOut, SnapshotOut

router = APIRouter()


def _release_detail(db: Session, snapshot: TaxonomySnapshot) -> ReleaseDetailOut:
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
        for v in artifacts.list_slots(db, snapshot)
    ]
    return ReleaseDetailOut(
        release=SnapshotOut.model_validate(snapshot),
        ready=artifacts.release_ready(snapshot),
        slots=slots,
    )


@router.get("/snapshots", response_model=list[SnapshotOut])
def list_snapshots(db: Session = Depends(get_db)) -> list[SnapshotOut]:
    # Reconcile status with what's on disk so the registry never shows "ready"
    # for a snapshot whose artifacts have gone missing.
    service.verify_all_snapshots(db)
    return [SnapshotOut.model_validate(s) for s in service.list_snapshots(db)]


@router.get("/snapshots/{snapshot_id}", response_model=SnapshotOut)
def get_snapshot(snapshot_id: int, db: Session = Depends(get_db)) -> SnapshotOut:
    snapshot = service.get_snapshot(db, snapshot_id)
    service.verify_snapshot(db, snapshot)
    return SnapshotOut.model_validate(snapshot)


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
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ReleaseDetailOut:
    """Upload a file into a slot (taxonomy package / filing rules / samples)."""
    snapshot = service.get_snapshot(db, snapshot_id)
    parsed = artifacts.parse_slot(slot)
    data = await file.read()
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
