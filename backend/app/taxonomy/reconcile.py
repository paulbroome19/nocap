"""On-demand recovery command for the taxonomy release store.

Run inside the deployed container (so it sees the mounted volume) to clear a
release stranded mid-creation — the residue that blocks re-uploading the same
DPM — and reconcile ready releases against what is on disk:

    railway run --service nocap python -m app.taxonomy.reconcile
    # or, in a container shell:
    python -m app.taxonomy.reconcile

It is idempotent and safe to run at any time. The same clean-up runs
automatically at startup (see app.main), so a redeploy already self-heals; this
is the manual lever for clearing without waiting for one.
"""

from __future__ import annotations

from app.core.db import SessionLocal
from app.taxonomy import service


def main() -> None:
    with SessionLocal() as db:
        cleared = service.clear_incomplete_creations(db)
        changed = service.verify_all_snapshots(db)
    print(
        f"reconcile: cleared {cleared} incomplete release(s); "
        f"reconciled {changed} snapshot(s) with disk."
    )


if __name__ == "__main__":
    main()
