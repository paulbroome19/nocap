"""Seed the workflow configs for our full reporting scope.

Module codes resolve against a snapshot at run time, so seeding does not require
any snapshot to exist. Idempotent: existing configs (by module code) are left
untouched. Run with:

    python -m app.workflows.seed
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.logging import configure_logging
from app.workflows.models import Entity, WorkflowConfig

logger = logging.getLogger(__name__)

# (name, framework_code, module_code) — module codes are the DPM ModuleVersion
# codes for our reporting scope.
WORKFLOW_SEED: list[tuple[str, str, str]] = [
    ("COREP — Own Funds", "COREP", "COREP_OF"),
    ("COREP — Leverage Ratio", "COREP", "COREP_LR"),
    ("COREP — Large Exposures", "COREP", "COREP_LE"),
    ("COREP — LCR (Delegated Act)", "COREP", "COREP_LCR_DA"),
    ("COREP — Additional Liquidity Monitoring", "COREP", "COREP_ALM"),
    ("COREP — NSFR (Stable Funding)", "COREP", "COREP_NSFR"),
    ("COREP — FRTB", "COREP", "COREP_FRTB"),
    ("Asset Encumbrance", "AE", "AE"),
    ("FINREP (IFRS9)", "FINREP", "FINREP9"),
    ("Pillar 3 — P3DH", "PILLAR3", "P3DH"),
    ("Investment Firms — Class 2", "IF", "IF_CLASS2"),
    ("Investment Firms — Class 3", "IF", "IF_CLASS3"),
    ("Investment Firms — Group Test", "IF", "IF_GROUPTEST"),
    ("Investment Firms — Threshold Monitoring", "IF", "IF_TM"),
    ("IRRBB", "IRRBB", "IRRBB"),
    ("Remuneration — High Earners (CI)", "REM", "REM_HE_CI"),
    ("Remuneration — Benchmarking (CI)", "REM", "REM_BM_CI"),
    ("Resolution 1", "RES", "RESOL1"),
    ("Resolution 2", "RES", "RESOL2"),
    ("MREL / TLAC", "MREL", "MREL_TLAC"),
]


# (name, LEI [20-char, valid format], country ISO, default scope) — fictional.
ENTITY_SEED: list[tuple[str, str, str, str]] = [
    ("Meridian Group Holdings plc", "213800MERIDNGRPHLD42", "GB", "CON"),
    ("Nordbank AG", "529900NORDBANKAG7X31", "DE", "IND"),
    ("Thistle Savings Bank plc", "213800THISTLESVBK019", "GB", "IND"),
]


def seed_entities(db: Session) -> int:
    """Insert any missing demo entities (idempotent by LEI). Returns count."""
    existing = set(db.scalars(select(Entity.lei)))
    inserted = 0
    for name, lei, country, default_scope in ENTITY_SEED:
        if lei in existing:
            continue
        db.add(
            Entity(name=name, lei=lei, country=country, default_scope=default_scope)
        )
        inserted += 1
    db.commit()
    return inserted


def seed_workflow_configs(db: Session) -> int:
    """Insert any missing workflow configs. Returns the number inserted."""
    existing = set(db.scalars(select(WorkflowConfig.module_code)))
    inserted = 0
    for name, framework_code, module_code in WORKFLOW_SEED:
        if module_code in existing:
            continue
        db.add(
            WorkflowConfig(
                name=name,
                framework_code=framework_code,
                module_code=module_code,
                active=True,
            )
        )
        inserted += 1
    db.commit()
    return inserted


def main() -> None:
    configure_logging()
    with SessionLocal() as db:
        configs = seed_workflow_configs(db)
        entities = seed_entities(db)
    logger.info("seeded %d workflow config(s), %d entity(ies)", configs, entities)
    print(f"seeded {configs} workflow config(s), {entities} entity(ies)")


if __name__ == "__main__":
    main()
