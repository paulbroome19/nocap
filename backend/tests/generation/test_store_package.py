"""Storing a generated package as a package_output RunFile (injected store)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.facts import service as facts_service
from app.facts.models import RunFile, RunFileRole
from app.generation.service import store_package
from tests.generation._helpers import metadata
from tests.generation.test_build_package import _FACTS, _MAP, build_package, resolver


def _store_run_file(db, run_id, filename, data):
    # Mirrors how the composition root/workflows will bind facts' store to the
    # package_output role, keeping generation decoupled from the facts stage.
    return facts_service.store_run_file(
        db,
        run_id=run_id,
        role=RunFileRole.package_output,
        filename=filename,
        data=data,
        settings=get_settings(),
    )


def test_store_package_creates_package_output_run_file(db_session: Session) -> None:
    pkg = build_package(_FACTS, metadata(), resolve=resolver(_MAP))
    run_file = store_package(
        db_session, run_id=7, package=pkg, store=_store_run_file
    )
    db_session.commit()

    assert run_file.role is RunFileRole.package_output
    assert run_file.filename == pkg.filename

    rows = db_session.query(RunFile).filter(RunFile.run_id == 7).all()
    assert len(rows) == 1
    assert rows[0].role is RunFileRole.package_output

    stored = get_settings().data_dir / rows[0].storage_key
    assert stored.exists() and stored.read_bytes() == pkg.content
