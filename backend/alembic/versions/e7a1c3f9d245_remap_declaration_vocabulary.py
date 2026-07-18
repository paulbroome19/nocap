"""remap filing-indicator declaration vocabulary

auto -> optional, true -> required, false -> not_required.

Revision ID: e7a1c3f9d245
Revises: d4f9a2c17e83
Create Date: 2026-07-18 16:20:00.000000
"""
from __future__ import annotations

import json
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

from app.workflows.declarations import remap_legacy_declarations


# revision identifiers, used by Alembic.
revision: str = 'e7a1c3f9d245'
down_revision: str | None = 'd4f9a2c17e83'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REVERSE = {'optional': 'auto', 'required': 'true', 'not_required': 'false'}


def _as_dict(value: object) -> dict:
    if isinstance(value, str):
        return json.loads(value) if value else {}
    return dict(value) if value else {}


def _rewrite(transform) -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, indicator_declarations FROM entity_workflow_config")
    ).fetchall()
    for rid, decl in rows:
        new = transform(_as_dict(decl))
        conn.execute(
            sa.text(
                "UPDATE entity_workflow_config "
                "SET indicator_declarations = CAST(:d AS JSON) WHERE id = :id"
            ),
            {"d": json.dumps(new), "id": rid},
        )


def upgrade() -> None:
    _rewrite(remap_legacy_declarations)


def downgrade() -> None:
    def to_legacy(d: dict) -> dict:
        return {k: _REVERSE.get(str(v), str(v)) for k, v in d.items()}

    _rewrite(to_legacy)
