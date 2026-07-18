"""regulator and release regulator_id FK

Revision ID: d4f9a2c17e83
Revises: c3d8f1a25b60
Create Date: 2026-07-18 15:40:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4f9a2c17e83'
down_revision: str | None = 'c3d8f1a25b60'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'regulator',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_regulator_code'), 'regulator', ['code'], unique=True
    )

    # Seed the EBA — a regulator FK is required, so the default publisher must
    # exist before the column is populated.
    regulator = sa.table(
        'regulator',
        sa.column('id', sa.Integer),
        sa.column('code', sa.String),
        sa.column('name', sa.String),
    )
    op.bulk_insert(
        regulator,
        [{'id': 1, 'code': 'EBA', 'name': 'European Banking Authority'}],
    )

    # Add the FK to releases: nullable first, backfill existing rows to the EBA,
    # then enforce NOT NULL so no release can exist without a publisher.
    op.add_column(
        'taxonomy_snapshot',
        sa.Column('regulator_id', sa.Integer(), nullable=True),
    )
    op.execute('UPDATE taxonomy_snapshot SET regulator_id = 1')
    op.alter_column('taxonomy_snapshot', 'regulator_id', nullable=False)
    op.create_index(
        op.f('ix_taxonomy_snapshot_regulator_id'),
        'taxonomy_snapshot', ['regulator_id'],
    )
    op.create_foreign_key(
        'fk_taxonomy_snapshot_regulator_id',
        'taxonomy_snapshot', 'regulator', ['regulator_id'], ['id'],
    )


def downgrade() -> None:
    op.drop_constraint(
        'fk_taxonomy_snapshot_regulator_id', 'taxonomy_snapshot',
        type_='foreignkey',
    )
    op.drop_index(
        op.f('ix_taxonomy_snapshot_regulator_id'),
        table_name='taxonomy_snapshot',
    )
    op.drop_column('taxonomy_snapshot', 'regulator_id')
    op.drop_index(op.f('ix_regulator_code'), table_name='regulator')
    op.drop_table('regulator')
