"""run capabilities snapshot

Revision ID: c3d8f1a25b60
Revises: b2c7e9d14a05
Create Date: 2026-07-18 13:05:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d8f1a25b60'
down_revision: str | None = 'b2c7e9d14a05'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The release capability set active when the run was created (reproducibility;
    # capabilities are otherwise derived on read, never stored).
    op.add_column('run', sa.Column('capabilities', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('run', 'capabilities')
