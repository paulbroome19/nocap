"""dpm source form provenance on snapshot

Records whether a release's DPM database was supplied as the original EBA
Access file (``accdb``) or a pre-converted SQLite (``sqlite``). Existing rows
predate the alternative input, so they backfill to ``accdb`` via the server
default.

Revision ID: a1b2c3d4e5f6
Revises: e7a1c3f9d245
Create Date: 2026-07-19 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = 'e7a1c3f9d245'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


dpm_source_form = sa.Enum('accdb', 'sqlite', name='dpm_source_form')


def upgrade() -> None:
    bind = op.get_bind()
    dpm_source_form.create(bind, checkfirst=True)
    op.add_column(
        'taxonomy_snapshot',
        sa.Column(
            'dpm_source_form',
            dpm_source_form,
            nullable=False,
            server_default='accdb',
        ),
    )


def downgrade() -> None:
    op.drop_column('taxonomy_snapshot', 'dpm_source_form')
    dpm_source_form.drop(op.get_bind(), checkfirst=True)
