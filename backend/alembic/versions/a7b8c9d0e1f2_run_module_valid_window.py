"""freeze the module version's validity window on the run

The report's out-of-window informational finding is read from the run itself, so
it stays reconstructible after the release (and its release_module rows) are
deleted. Backfills existing runs from the current release_module where a matching
row still exists; runs whose release is gone stay NULL.

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-07-19 23:20:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: str | None = 'f1a2b3c4d5e6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('run', sa.Column('module_valid_from', sa.Date(), nullable=True))
    op.add_column('run', sa.Column('module_valid_to', sa.Date(), nullable=True))

    # Backfill from the release's recorded module (matched by the run's release
    # and its workflow's module), where those rows still exist.
    op.execute(
        """
        UPDATE run
        SET module_valid_from = rm.valid_from,
            module_valid_to   = rm.valid_to
        FROM release_module rm, workflow_config wc
        WHERE wc.id = run.workflow_id
          AND rm.snapshot_id = run.snapshot_id
          AND rm.module_code = wc.module_code
        """
    )


def downgrade() -> None:
    op.drop_column('run', 'module_valid_to')
    op.drop_column('run', 'module_valid_from')
