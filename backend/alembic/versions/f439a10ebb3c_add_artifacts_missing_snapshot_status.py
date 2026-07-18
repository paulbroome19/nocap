"""add artifacts_missing snapshot status

Revision ID: f439a10ebb3c
Revises: 7f7eed6fc5af
Create Date: 2026-07-18 01:09:48.308334
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f439a10ebb3c'
down_revision: str | None = '7f7eed6fc5af'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add the new value to the Postgres enum. IF NOT EXISTS makes it idempotent.
    op.execute(
        "ALTER TYPE snapshot_status ADD VALUE IF NOT EXISTS 'artifacts_missing'"
    )


def downgrade() -> None:
    # Postgres cannot drop a value from an enum type; removing it would require
    # recreating the type and rewriting the column. Left as a no-op.
    pass
