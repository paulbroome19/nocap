"""validation_rules slot and validation_rule table

Revision ID: b2c7e9d14a05
Revises: a8c3e1d290f5
Create Date: 2026-07-18 12:20:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c7e9d14a05'
down_revision: str | None = 'a8c3e1d290f5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # New functional slot on a release. IF NOT EXISTS makes it idempotent; the
    # value is not used within this transaction (validation_rule has no slot
    # column), so it is safe to add here.
    op.execute(
        "ALTER TYPE release_slot ADD VALUE IF NOT EXISTS 'validation_rules'"
    )

    # A projection of the ingested validation-rules workbook. Deliberately NOT
    # unique on (snapshot_id, vr_code): the workbook is date/module-versioned so
    # one code has several windowed rows. Indexed as a lookup key instead.
    op.create_table(
        'validation_rule',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('snapshot_id', sa.Integer(), nullable=False),
        sa.Column('vr_code', sa.String(length=64), nullable=False),
        sa.Column('source', sa.String(length=64), nullable=True),
        sa.Column('frameworks', sa.String(length=255), nullable=True),
        sa.Column('modules', sa.Text(), nullable=True),
        sa.Column('cross_module', sa.String(length=8), nullable=True),
        sa.Column('tables', sa.Text(), nullable=True),
        sa.Column('expression', sa.Text(), nullable=True),
        sa.Column('precondition', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('from_reference_date', sa.Date(), nullable=True),
        sa.Column('to_reference_date', sa.Date(), nullable=True),
        sa.Column('severity', sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(['snapshot_id'], ['taxonomy_snapshot.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_validation_rule_snapshot_id'),
        'validation_rule', ['snapshot_id'],
    )
    op.create_index(
        'ix_validation_rule_snapshot_vr',
        'validation_rule', ['snapshot_id', 'vr_code'],
    )


def downgrade() -> None:
    op.drop_index('ix_validation_rule_snapshot_vr', table_name='validation_rule')
    op.drop_index(
        op.f('ix_validation_rule_snapshot_id'), table_name='validation_rule'
    )
    op.drop_table('validation_rule')
    # Postgres cannot drop a value from an enum type; left as a no-op (mirrors
    # the artifacts_missing migration).