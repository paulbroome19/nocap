"""Application configuration.

Twelve-factor: all configuration comes from environment variables (or a local
``.env`` for development). No secrets in the repo. The app must not care where
it runs.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The backend package root (.../backend), used to anchor relative storage paths
# so the data dir does not depend on the process's current working directory.
_BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime settings, populated from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Carter"
    environment: str = "development"
    debug: bool = False

    # ISO 2-letter reporting country used in generated package filenames (the
    # reporting country isn't captured per-entity in v1). Overridable per run.
    default_country: str = "XX"

    # SQLAlchemy 2.x + psycopg (v3) driver against local Postgres by default.
    # A managed provider (e.g. Railway) hands out a plain ``postgresql://`` (or
    # ``postgres://``) URL; SQLAlchemy would then reach for psycopg2, which we do
    # not install. The validator below rewrites those to the psycopg v3 driver so
    # the provider's DATABASE_URL works verbatim, no secret rewriting required.
    # Local-dev database name stays ``nocap`` (the project's pre-rename name):
    # existing local databases hold their data there, and this default only ever
    # applies to local dev — a managed provider (Railway) supplies its own
    # DATABASE_URL (its DB is named ``railway``), so this value never reaches
    # production.
    database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/nocap"
    )

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        for prefix in ("postgresql://", "postgres://"):
            if value.startswith(prefix):
                rest = value[len(prefix):]
                return f"postgresql+psycopg://{rest}"
        return value

    log_level: str = "INFO"

    # Where uploaded DPM snapshots are stored on disk (one subdir per snapshot
    # id). Snapshots are sealed, reproducible artifacts — keep this on durable
    # storage in production. Twelve-factor: overridable via DATA_DIR. Resolved to
    # an absolute path (relative values anchor to backend/, not the cwd) so the
    # storage root is stable regardless of where the process is launched.
    data_dir: Path = _BACKEND_DIR / "data"

    @field_validator("data_dir")
    @classmethod
    def _resolve_data_dir(cls, value: Path) -> Path:
        value = Path(value).expanduser()
        if not value.is_absolute():
            value = _BACKEND_DIR / value
        return value.resolve()

    # Built frontend (Vite ``dist``) to serve as static files so one service
    # hosts the whole app. Defaults to ``frontend/dist`` beside the backend; the
    # container sets STATIC_DIR to wherever the build was copied. When the dir is
    # absent (local dev with the Vite dev server), static serving is skipped.
    static_dir: Path = _BACKEND_DIR.parent / "frontend" / "dist"

    @field_validator("static_dir")
    @classmethod
    def _resolve_static_dir(cls, value: Path) -> Path:
        value = Path(value).expanduser()
        if not value.is_absolute():
            value = _BACKEND_DIR / value
        return value.resolve()

    # mdbtools binaries used to convert the EBA DPM Access (.accdb) release into
    # a per-snapshot SQLite file on ingest. Overridable if not on PATH.
    mdb_schema_bin: str = "mdb-schema"
    mdb_export_bin: str = "mdb-export"

    # On startup, reconcile snapshot status with on-disk artifacts. Disabled in
    # tests (which use their own DB session, not the app's engine).
    reconcile_snapshots_on_startup: bool = True

    # On startup, refuse to serve if the database isn't at the migration head
    # (fail fast with a clear message instead of per-request 500s). Disabled in
    # tests, which build the schema with create_all rather than migrations.
    check_schema_on_startup: bool = True

    # Arelle EBA formula validation (v2). Feature flag to disable entirely; the
    # per-snapshot taxonomy package(s) live in the snapshot's artifact slot.
    arelle_enabled: bool = True
    # NB: an in-process persistent taxonomy-model cache was investigated and
    # deliberately NOT shipped — a reused Arelle controller is neither faster
    # (the DTS is re-parsed every load) nor reproducible (findings differ across
    # runs). See docs/formula-cache-findings.md for the evidence + the
    # out-of-process path that would be required.

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / "snapshots"


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance."""
    return Settings()
