"""Startup schema-version guard."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from app.core.schema import (
    SchemaOutOfDateError,
    check_schema_current,
    code_heads,
)


def test_code_heads_is_single_head() -> None:
    # A linear migration history has exactly one head.
    heads = code_heads()
    assert len(heads) == 1


def test_empty_database_is_rejected(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'empty.sqlite'}")
    with pytest.raises(SchemaOutOfDateError, match="out of date"):
        check_schema_current(engine)


def test_database_stamped_at_head_passes(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'stamped.sqlite'}")
    head = next(iter(code_heads()))
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        conn.execute(
            text("INSERT INTO alembic_version VALUES (:v)"), {"v": head}
        )
    check_schema_current(engine)  # must not raise


def test_database_at_wrong_revision_is_rejected(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'stale.sqlite'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        conn.execute(text("INSERT INTO alembic_version VALUES ('deadbeef0000')"))
    with pytest.raises(SchemaOutOfDateError):
        check_schema_current(engine)
