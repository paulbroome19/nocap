"""entity workflow config

Revision ID: d5f2b0e8c3a1
Revises: c4e1a9d7b2f0
Create Date: 2026-07-18 09:40:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5f2b0e8c3a1'
down_revision: str | None = 'c4e1a9d7b2f0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'entity_workflow_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('workflow_id', sa.Integer(), nullable=False),
        sa.Column(
            'indicator_declarations', sa.JSON(), nullable=False,
            server_default='{}',
        ),
        sa.Column('base_currency', sa.String(length=3), nullable=True),
        sa.Column('decimals', sa.Integer(), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.ForeignKeyConstraint(['entity_id'], ['entity.id']),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflow_config.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'entity_id', 'workflow_id', name='uq_entity_workflow_config'
        ),
    )
    op.create_index(
        op.f('ix_entity_workflow_config_entity_id'),
        'entity_workflow_config', ['entity_id'],
    )
    op.create_index(
        op.f('ix_entity_workflow_config_workflow_id'),
        'entity_workflow_config', ['workflow_id'],
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_entity_workflow_config_workflow_id'),
        table_name='entity_workflow_config',
    )
    op.drop_index(
        op.f('ix_entity_workflow_config_entity_id'),
        table_name='entity_workflow_config',
    )
    op.drop_table('entity_workflow_config')
