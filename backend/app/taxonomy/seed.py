"""Seed the taxonomy publishers (regulators).

A regulator is the body that publishes the taxonomy releases we ingest. The
platform ships with the EBA; more publishers are new rows, no code changes.
Idempotent (matched by code). Run with:

    python -m app.taxonomy.seed
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.logging import configure_logging
from app.taxonomy.models import Regulator

logger = logging.getLogger(__name__)

# (code, name) — publishers of the taxonomies NoCap ingests.
REGULATOR_SEED: list[tuple[str, str]] = [
    ("EBA", "European Banking Authority"),
]


def seed_regulators(db: Session) -> int:
    """Insert any missing regulators (idempotent by code). Returns count."""
    existing = set(db.scalars(select(Regulator.code)))
    inserted = 0
    for code, name in REGULATOR_SEED:
        if code in existing:
            continue
        db.add(Regulator(code=code, name=name))
        inserted += 1
    db.commit()
    return inserted


def eba(db: Session) -> Regulator:
    """The EBA regulator row, seeding it if absent (the default publisher)."""
    seed_regulators(db)
    return db.scalar(select(Regulator).where(Regulator.code == "EBA"))


def main() -> None:
    configure_logging()
    with SessionLocal() as db:
        count = seed_regulators(db)
    logger.info("seeded %d regulator(s)", count)
    print(f"seeded {count} regulator(s)")


if __name__ == "__main__":
    main()
