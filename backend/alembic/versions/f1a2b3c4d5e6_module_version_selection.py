"""release_module table + run module/framework version + rule scope

Records, per release, the module versions it provides (from the DPM's own
current release) — the user-selectable surface for taxonomy version selection.
Runs freeze the module_version, framework_version, and rule scope they used.

Revision ID: f1a2b3c4d5e6
Revises: e5b28d1c9a34
Create Date: 2026-07-19 22:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: str | None = 'e5b28d1c9a34'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'release_module',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('snapshot_id', sa.Integer(), nullable=False),
        sa.Column('module_code', sa.String(length=128), nullable=False),
        sa.Column('framework_code', sa.String(length=64), nullable=False),
        sa.Column('module_name', sa.String(length=512), nullable=True),
        sa.Column('module_version', sa.String(length=32), nullable=False),
        sa.Column('framework_version', sa.String(length=32), nullable=False),
        sa.Column('valid_from', sa.Date(), nullable=True),
        sa.Column('valid_to', sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(
            ['snapshot_id'], ['taxonomy_snapshot.id'],
            name='fk_release_module_snapshot',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_release_module_snapshot', 'release_module', ['snapshot_id']
    )
    op.create_index(
        'ix_release_module_code', 'release_module', ['module_code']
    )

    op.add_column(
        'run', sa.Column('module_version', sa.String(length=32), nullable=True)
    )
    op.add_column(
        'run',
        sa.Column('framework_version', sa.String(length=32), nullable=True),
    )
    op.add_column('run', sa.Column('rule_scope', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('run', 'rule_scope')
    op.drop_column('run', 'framework_version')
    op.drop_column('run', 'module_version')
    op.drop_index('ix_release_module_code', table_name='release_module')
    op.drop_index('ix_release_module_snapshot', table_name='release_module')
    op.drop_table('release_module')
