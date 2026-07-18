"""Shared test fixtures.

Tests run fully hermetic: the app database is a temp SQLite file (not Postgres),
the snapshot data dir is a temp dir, and DPM lookups use a tiny generated
fixture database — never the real EBA release.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Import models so their tables register on Base.metadata before create_all.
import app.taxonomy.models  # noqa: F401
from app.core.config import get_settings
from app.core.db import Base, get_db
from app.main import app
from tests.fixtures import dpm_mini


@pytest.fixture(autouse=True)
def _data_dir(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """Point the app's DATA_DIR at a fresh temp dir for each test.

    Per-test (not per-session): snapshot ids reset with the fresh app DB every
    test, so a shared data dir would collide on ``snapshots/1``.
    """
    d = tmp_path_factory.mktemp("nocap-data")
    os.environ["DATA_DIR"] = str(d)
    # The startup reconcile uses the app's own engine (real Postgres); keep tests
    # hermetic by disabling it — verify_all_snapshots is unit-tested directly.
    os.environ["RECONCILE_SNAPSHOTS_ON_STARTUP"] = "false"
    get_settings.cache_clear()
    yield d
    get_settings.cache_clear()


@pytest.fixture
def engine(tmp_path: Path):
    eng = create_engine(f"sqlite:///{tmp_path / 'app.sqlite'}", future=True)
    Base.metadata.create_all(eng)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def db_session(engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    """A TestClient whose get_db yields the test session."""
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def mini_dpm(tmp_path: Path) -> Path:
    """A tiny fixture DPM SQLite database (see tests/fixtures/dpm_mini.py)."""
    return dpm_mini.build(tmp_path / "dpm_mini.sqlite")
