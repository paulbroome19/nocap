"""Application configuration.

Twelve-factor: all configuration comes from environment variables (or a local
``.env`` for development). No secrets in the repo. The app must not care where
it runs.
"""

from __future__ import annotations

from functools import lru_cache

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

    # SQLAlchemy 2.x + psycopg (v3) driver against local Postgres by default.
    database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/nocap"
    )

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance."""
    return Settings()
