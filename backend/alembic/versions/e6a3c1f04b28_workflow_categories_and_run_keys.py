"""workflow categories, is_active, and run instance keys

Revision ID: e6a3c1f04b28
Revises: d5f2b0e8c3a1
Create Date: 2026-07-18 12:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6a3c1f04b28'
down_revision: str | None = 'd5f2b0e8c3a1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # WorkflowConfig: category + rename active -> is_active.
    op.add_column(
        'workflow_config', sa.Column('category', sa.String(length=64), nullable=True)
    )
    op.alter_column('workflow_config', 'active', new_column_name='is_active')

    # Run: three free-text instance keys.
    op.add_column(
        'run', sa.Column('snapshot_key', sa.String(length=128), nullable=True)
    )
    op.add_column(
        'run', sa.Column('adjusted_key', sa.String(length=128), nullable=True)
    )
    op.add_column(
        'run', sa.Column('version_key', sa.String(length=128), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('run', 'version_key')
    op.drop_column('run', 'adjusted_key')
    op.drop_column('run', 'snapshot_key')

    op.alter_column('workflow_config', 'is_active', new_column_name='active')
    op.drop_column('workflow_config', 'category')
