"""output format configuration

Per-(regulator, workflow) output format with a regulator-level default, plus the
format a run was generated in.

Revision ID: b8d3f21a0c67
Revises: e7a1c3f9d245
Create Date: 2026-07-19 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8d3f21a0c67'
down_revision: str | None = 'e7a1c3f9d245'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The first create_table owns creation of the Postgres enum type; every
    # reference after it is create_type=False so the type isn't re-created.
    of_create = sa.Enum('xbrl_csv', 'xbrl_xml', name='output_format')
    of = sa.Enum('xbrl_csv', 'xbrl_xml', name='output_format', create_type=False)

    op.create_table(
        'regulator_format_default',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('regulator_id', sa.Integer(), nullable=False),
        sa.Column('output_format', of_create, nullable=False),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.ForeignKeyConstraint(['regulator_id'], ['regulator.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('regulator_id'),
    )
    op.create_table(
        'workflow_format_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('regulator_id', sa.Integer(), nullable=False),
        sa.Column('workflow_id', sa.Integer(), nullable=False),
        sa.Column('output_format', of, nullable=False),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.ForeignKeyConstraint(['regulator_id'], ['regulator.id']),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflow_config.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'regulator_id', 'workflow_id', name='uq_workflow_format_config'
        ),
    )
    op.create_index(
        op.f('ix_workflow_format_config_regulator_id'),
        'workflow_format_config', ['regulator_id'],
    )
    op.create_index(
        op.f('ix_workflow_format_config_workflow_id'),
        'workflow_format_config', ['workflow_id'],
    )

    op.add_column('run', sa.Column('output_format', of, nullable=True))


def downgrade() -> None:
    op.drop_column('run', 'output_format')
    op.drop_index(
        op.f('ix_workflow_format_config_workflow_id'),
        table_name='workflow_format_config',
    )
    op.drop_index(
        op.f('ix_workflow_format_config_regulator_id'),
        table_name='workflow_format_config',
    )
    op.drop_table('workflow_format_config')
    op.drop_table('regulator_format_default')
    # Postgres: drop the enum type so a re-upgrade can recreate it.
    sa.Enum(name='output_format').drop(op.get_bind(), checkfirst=True)
