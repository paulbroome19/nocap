"""run filing indicator outcomes

Revision ID: f7b2d9c0a1e4
Revises: e6a3c1f04b28
Create Date: 2026-07-18 13:10:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7b2d9c0a1e4'
down_revision: str | None = 'e6a3c1f04b28'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('run', sa.Column('filing_indicators', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('run', 'filing_indicators')
