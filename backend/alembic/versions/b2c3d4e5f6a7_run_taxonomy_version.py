"""freeze the taxonomy version (bound release) on the run

The user selects a taxonomy version (the release, e.g. "4.2.1"); the run records
the specific release it bound to. Frozen here so every label leads with the
taxonomy version and reproduces after the release is deleted. Backfills existing
runs from the bound snapshot's version_label where it still exists.

Revision ID: b2c3d4e5f6a7
Revises: a7b8c9d0e1f2
Create Date: 2026-07-19 23:55:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: str | None = 'a7b8c9d0e1f2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'run', sa.Column('taxonomy_version', sa.String(length=64), nullable=True)
    )
    op.execute(
        """
        UPDATE run
        SET taxonomy_version = ts.version_label
        FROM taxonomy_snapshot ts
        WHERE ts.id = run.snapshot_id
        """
    )


def downgrade() -> None:
    op.drop_column('run', 'taxonomy_version')
