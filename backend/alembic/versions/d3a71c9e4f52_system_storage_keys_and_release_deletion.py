"""system storage keys + allow release deletion

Two changes:

**E1 — system storage keys.** Re-keys existing ``run_file`` and
``release_artifact`` rows to system-generated on-disk names (independent of the
user's filename) and moves each file to its new name in place. The move is
defensive: a row whose file is already missing is left untouched (its file was
gone before this ran; reconciliation reports it). The display filename column is
unchanged. Not reversible (original filename-based keys cannot be reconstructed);
downgrade is a no-op for this part.

**A2 — allow release deletion.** Drops the ``run.snapshot_id`` foreign key so a
release referenced by runs can be deleted (runs are frozen and keep their own
copies; ``snapshot_id`` stays as frozen provenance). Downgrade re-adds the FK.

Revision ID: d3a71c9e4f52
Revises: c9e4b1f7a208
Create Date: 2026-07-19 16:00:00.000000
"""
from __future__ import annotations

import os
import uuid
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd3a71c9e4f52'
down_revision: str | None = 'c9e4b1f7a208'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _rekey_table(bind, data_dir: Path, table: str) -> None:
    """Re-key one table's artifacts to system names, moving files in place."""
    rows = bind.execute(
        sa.text(f"SELECT id, filename, storage_key FROM {table}")  # noqa: S608
    ).fetchall()
    for row_id, filename, key in rows:
        if not key:
            continue
        old_path = data_dir / key
        if not old_path.is_file():
            continue  # file already missing — leave the row as-is
        suffix = Path(filename or key).suffix.lower()
        parent = Path(key).parent  # keep the same directory structure
        new_key = (parent / f"{uuid.uuid4().hex}{suffix}").as_posix()
        new_path = data_dir / new_key
        new_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(old_path, new_path)
        bind.execute(
            sa.text(  # noqa: S608
                f"UPDATE {table} SET storage_key = :k WHERE id = :i"
            ),
            {"k": new_key, "i": row_id},
        )


def upgrade() -> None:
    # E1 — re-key existing artifacts to system storage keys (moves files).
    from app.core.config import get_settings

    data_dir = Path(get_settings().data_dir)
    bind = op.get_bind()
    for table in ("run_file", "release_artifact"):
        _rekey_table(bind, data_dir, table)

    # A2 — drop the run.snapshot_id FK so a referenced release can be deleted.
    op.drop_constraint('run_snapshot_id_fkey', 'run', type_='foreignkey')


def downgrade() -> None:
    op.create_foreign_key(
        'run_snapshot_id_fkey', 'run', 'taxonomy_snapshot',
        ['snapshot_id'], ['id'],
    )
    # The E1 re-key is not reversed (original filename-based keys are lost).
