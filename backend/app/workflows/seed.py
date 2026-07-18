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

# (name, framework_code, module_code, category, is_active) — module codes are the
# DPM ModuleVersion codes. Active suites show in the Reporting UI under their
# category; inactive ones only appear in Settings. Display names are clean (no
# "COREP —" prefix); the module code stays as the technical subtitle in the UI.
WORKFLOW_SEED: list[tuple[str, str, str, str | None, bool]] = [
    # Liquidity
    ("LCR", "COREP", "COREP_LCR_DA", "Liquidity", True),
    ("NSFR", "COREP", "COREP_NSFR", "Liquidity", True),
    ("Additional Liquidity Monitoring", "COREP", "COREP_ALM", "Liquidity", True),
    ("Asset Encumbrance", "AE", "AE", "Liquidity", True),
    # Capital
    ("Own Funds", "COREP", "COREP_OF", "Capital", True),
    ("Leverage Ratio", "COREP", "COREP_LR", "Capital", True),
    ("Large Exposures", "COREP", "COREP_LE", "Capital", True),
    ("FRTB", "COREP", "COREP_FRTB", "Capital", True),
    # Financial
    ("FINREP", "FINREP", "FINREP9", "Financial", True),
    # Last Mile Reporting
    ("Investment Firms", "IF", "IF_CLASS2", "Last Mile Reporting", True),
    ("IRRBB", "IRRBB", "IRRBB", "Last Mile Reporting", True),
    ("Pillar 3", "PILLAR3", "P3DH", "Last Mile Reporting", True),
    ("Remuneration — High Earners", "REM", "REM_HE_CI", "Last Mile Reporting", True),
    ("Resolution", "RES", "RESOL2", "Last Mile Reporting", True),
    # Inactive — hidden from Reporting, editable in Settings.
    ("Investment Firms — Class 3", "IF", "IF_CLASS3", None, False),
    ("Investment Firms — Group Test", "IF", "IF_GROUPTEST", None, False),
    ("Investment Firms — Threshold Monitoring", "IF", "IF_TM", None, False),
    ("Remuneration — Benchmarking (CI)", "REM", "REM_BM_CI", None, False),
    ("Resolution 1", "RES", "RESOL1", None, False),
    ("MREL / TLAC", "MREL", "MREL_TLAC", None, False),
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
    """Upsert the workflow configs. Returns the number newly inserted.

    Existing rows (matched by module code) are updated in place — name, category,
    framework, and is_active — so re-seeding applies the current catalogue (clean
    display names + categories) to an already-seeded database.
    """
    existing = {w.module_code: w for w in db.scalars(select(WorkflowConfig))}
    inserted = 0
    for name, framework_code, module_code, category, is_active in WORKFLOW_SEED:
        wf = existing.get(module_code)
        if wf is None:
            db.add(
                WorkflowConfig(
                    name=name,
                    framework_code=framework_code,
                    module_code=module_code,
                    category=category,
                    is_active=is_active,
                )
            )
            inserted += 1
        else:
            wf.name = name
            wf.framework_code = framework_code
            wf.category = category
            wf.is_active = is_active
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
