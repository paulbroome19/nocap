"""run formula validation summary

Revision ID: a8c3e1d290f5
Revises: f7b2d9c0a1e4
Create Date: 2026-07-18 14:20:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8c3e1d290f5'
down_revision: str | None = 'f7b2d9c0a1e4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('run', sa.Column('formula_summary', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('run', 'formula_summary')
