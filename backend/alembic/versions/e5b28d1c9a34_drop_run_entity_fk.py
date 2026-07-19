"""drop run.entity_id FK so entities can be deleted

Entities are live reference data and are now freely deletable. Runs freeze the
entity's values (name, LEI, scope, country) at execution and keep them; the
``entity_id`` is retained only as historical provenance (it may point at a
since-deleted entity), so the foreign key is dropped. Downgrade re-adds it.

Revision ID: e5b28d1c9a34
Revises: d3a71c9e4f52
Create Date: 2026-07-19 18:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5b28d1c9a34'
down_revision: str | None = 'd3a71c9e4f52'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint('fk_run_entity', 'run', type_='foreignkey')


def downgrade() -> None:
    op.create_foreign_key(
        'fk_run_entity', 'run', 'entity', ['entity_id'], ['id']
    )
