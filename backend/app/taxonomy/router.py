"""HTTP routes for the taxonomy stage — thin: parse, call service, shape response.

Snapshot registry + DPM upload. Ingestion (Access -> SQLite conversion) runs as
a background task; clients poll the snapshot detail for status.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.taxonomy import service
from app.taxonomy.schemas import SnapshotOut

router = APIRouter()


@router.get("/snapshots", response_model=list[SnapshotOut])
def list_snapshots(db: Session = Depends(get_db)) -> list[SnapshotOut]:
    return [SnapshotOut.model_validate(s) for s in service.list_snapshots(db)]


@router.get("/snapshots/{snapshot_id}", response_model=SnapshotOut)
def get_snapshot(snapshot_id: int, db: Session = Depends(get_db)) -> SnapshotOut:
    return SnapshotOut.model_validate(service.get_snapshot(db, snapshot_id))


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
