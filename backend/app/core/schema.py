"""Startup schema-version guard.

Refuse to serve on a database that isn't at the migration head: fail fast with a
clear "run alembic upgrade head" message instead of letting every request 500 on
a missing column. Pure infrastructure — no models, no business logic.
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine

logger = logging.getLogger(__name__)

# backend/alembic — holds env.py + versions/.
_ALEMBIC_DIR = Path(__file__).resolve().parents[2] / "alembic"


class SchemaOutOfDateError(RuntimeError):
    """Raised when the database is not at the code's migration head."""


def code_heads() -> set[str]:
    """The migration head(s) the code base declares."""
    config = Config()
    config.set_main_option("script_location", str(_ALEMBIC_DIR))
    return set(ScriptDirectory.from_config(config).get_heads())


def db_heads(engine: Engine) -> set[str]:
    """The migration revision(s) the database is currently stamped at."""
    with engine.connect() as conn:
        return set(MigrationContext.configure(conn).get_current_heads())


def check_schema_current(engine: Engine) -> None:
    """Raise ``SchemaOutOfDateError`` unless the DB is at the code's head.

    Covers both a database behind the code (missing migrations) and one ahead of
    it (deployed with an older image) — either way the schema and code disagree.
    """
    expected = code_heads()
    actual = db_heads(engine)
    if actual != expected:
        raise SchemaOutOfDateError(
            "database schema out of date — run `alembic upgrade head` "
            f"(database at {sorted(actual) or ['(empty)']}, "
            f"code expects {sorted(expected)})"
        )
    logger.info("database schema at head %s", sorted(expected))
