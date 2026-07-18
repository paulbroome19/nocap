"""release artifact slots

Revision ID: c4e1a9d7b2f0
Revises: f5845162cbcc
Create Date: 2026-07-18 09:10:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e1a9d7b2f0'
down_revision: str | None = 'f5845162cbcc'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


release_slot = sa.Enum(
    'dpm_database', 'taxonomy_package', 'filing_rules', 'sample_files',
    name='release_slot',
)
artifact_status = sa.Enum(
    'empty', 'uploaded', 'verifying', 'ready', 'failed', name='artifact_status',
)


def upgrade() -> None:
    bind = op.get_bind()
    release_slot.create(bind, checkfirst=True)
    artifact_status.create(bind, checkfirst=True)
    op.create_table(
        'release_artifact',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('snapshot_id', sa.Integer(), nullable=False),
        sa.Column('slot', release_slot, nullable=False),
        sa.Column('filename', sa.String(length=1024), nullable=False),
        sa.Column('storage_key', sa.String(length=2048), nullable=False),
        sa.Column('checksum', sa.String(length=64), nullable=False),
        sa.Column(
            'status', artifact_status, nullable=False, server_default='uploaded'
        ),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column(
            'uploaded_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.ForeignKeyConstraint(['snapshot_id'], ['taxonomy_snapshot.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'snapshot_id', 'slot', name='uq_release_artifact_slot'
        ),
    )
    op.create_index(
        op.f('ix_release_artifact_snapshot_id'),
        'release_artifact', ['snapshot_id'],
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_release_artifact_snapshot_id'), table_name='release_artifact'
    )
    op.drop_table('release_artifact')
    bind = op.get_bind()
    artifact_status.drop(bind, checkfirst=True)
    release_slot.drop(bind, checkfirst=True)
