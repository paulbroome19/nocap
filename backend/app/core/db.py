"""Database engine, session factory, and declarative base.

This is infrastructure only — no models and no business logic live here. Stage
packages define their own ``models.py`` against :class:`Base`.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Declarative base shared by every model in the app.

    Alembic's autogenerate targets ``Base.metadata``; every stage's models must
    import from here so migrations see them.
    """


settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a session and closing it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
