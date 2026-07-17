"""Application configuration.

Twelve-factor: all configuration comes from environment variables (or a local
``.env`` for development). No secrets in the repo. The app must not care where
it runs.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings, populated from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "NoCap"
    environment: str = "development"
    debug: bool = False

    # ISO 2-letter reporting country used in generated package filenames (the
    # reporting country isn't captured per-entity in v1). Overridable per run.
    default_country: str = "XX"

    # SQLAlchemy 2.x + psycopg (v3) driver against local Postgres by default.
    database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/nocap"
    )

    log_level: str = "INFO"

    # Where uploaded DPM snapshots are stored on disk (one subdir per snapshot
    # id). Snapshots are sealed, reproducible artifacts — keep this on durable
    # storage in production. Twelve-factor: overridable via DATA_DIR.
    data_dir: Path = Path("./data")

    # mdbtools binaries used to convert the EBA DPM Access (.accdb) release into
    # a per-snapshot SQLite file on ingest. Overridable if not on PATH.
    mdb_schema_bin: str = "mdb-schema"
    mdb_export_bin: str = "mdb-export"

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / "snapshots"


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance."""
    return Settings()
