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
from app.workflows.models import WorkflowConfig

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
        inserted = seed_workflow_configs(db)
    logger.info("seeded %d workflow config(s)", inserted)
    print(f"seeded {inserted} workflow config(s)")


if __name__ == "__main__":
    main()
