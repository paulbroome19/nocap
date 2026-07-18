"""formula validation phase and run status

Revision ID: f5845162cbcc
Revises: 61a7794b6040
Create Date: 2026-07-18 09:56:27.911425
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f5845162cbcc'
down_revision: str | None = '61a7794b6040'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # New enum values for the Arelle formula validation phase (Alembic can't
    # autogenerate these). IF NOT EXISTS makes them idempotent.
    op.execute(
        "ALTER TYPE run_status ADD VALUE IF NOT EXISTS 'formula_validation_running'"
    )
    op.execute(
        "ALTER TYPE validation_phase ADD VALUE IF NOT EXISTS 'formula'"
    )


def downgrade() -> None:
    # Postgres cannot drop enum values; left as a no-op.
    pass
