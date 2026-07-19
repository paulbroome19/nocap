"""merge dpm_source_form and output_format heads

Two migrations branched from e7a1c3f9d245 and landed on main independently:
a1b2c3d4e5f6 (DPM source form) and b8d3f21a0c67 (output-format config). They
touch disjoint tables, so this is a no-op merge point that rejoins the history
into a single head — no schema change of its own.

Revision ID: a56f7faf3e96
Revises: a1b2c3d4e5f6, b8d3f21a0c67
Create Date: 2026-07-19 10:24:59.516977
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a56f7faf3e96'
down_revision: str | None = ('a1b2c3d4e5f6', 'b8d3f21a0c67')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
