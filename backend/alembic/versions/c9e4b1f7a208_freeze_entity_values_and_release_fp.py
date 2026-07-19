"""freeze entity values and release fingerprint on run

Adds ``run.entity_name`` and ``run.release_fingerprint``.

``entity_name`` freezes the entity's display name onto the run (the LEI, scope,
and country were already frozen), so a later rename / edit / deletion of the
entity never alters a historical execution. Existing rows are backfilled from
the current ``entity`` row — the best available truth. **Limitation:** for a run
whose entity was renamed *before* this migration, the backfilled name is the
entity's *current* name, not the name as it was at that run's execution; that
history cannot be recovered.

``release_fingerprint`` records a content fingerprint of the bound release's
artifacts so a new execution can detect that an artifact was replaced. It is
left NULL for existing runs (no baseline can be reconstructed): the dependency
guard treats a NULL fingerprint as "no baseline", so release-artifact changes
are not flagged on the first re-execution of a pre-existing run. New runs record
it and are fully covered.

Revision ID: c9e4b1f7a208
Revises: a56f7faf3e96
Create Date: 2026-07-19 14:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c9e4b1f7a208'
down_revision: str | None = 'a56f7faf3e96'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'run', sa.Column('entity_name', sa.String(length=255), nullable=True)
    )
    op.add_column(
        'run',
        sa.Column('release_fingerprint', sa.String(length=64), nullable=True),
    )
    # Backfill entity_name from the current entity row (best available truth).
    op.execute(
        "UPDATE run SET entity_name = ("
        "SELECT name FROM entity WHERE entity.id = run.entity_id"
        ") WHERE entity_id IS NOT NULL AND entity_name IS NULL"
    )


def downgrade() -> None:
    op.drop_column('run', 'release_fingerprint')
    op.drop_column('run', 'entity_name')
