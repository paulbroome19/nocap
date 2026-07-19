"""A run dispatches generation on the configured output format."""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from datetime import date

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.facts.models import RunFileRole
from app.generation.schemas import OutputFormat
from app.taxonomy.models import TaxonomySnapshot
from app.workflows import service
from app.workflows.models import Entity, RunStatus, WorkflowConfig


def _run(db, snapshot, workflow, entity):
    return service.create_run(
        db,
        workflow_id=workflow.id,
        snapshot_id=snapshot.id,
        reference_date=date(2025, 12, 31),
        entity_id=entity.id,
    )


def _package(db, run_id) -> zipfile.ZipFile:
    out = next(
        f
        for f in service.run_files(db, run_id)
        if f.role is RunFileRole.package_output
    )
    return zipfile.ZipFile(get_settings().data_dir / out.storage_key)


def test_csv_is_the_default(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
    demo_fact_xlsx: bytes,
) -> None:
    run = _run(db_session, ready_snapshot, lcr_workflow, entity)
    service.attach_fact_file(
        db_session, run_id=run.id, filename="facts.xlsx", data=demo_fact_xlsx
    )
    run = service.execute_run(db_session, run.id)
    assert run.status is RunStatus.generated, run.error
    assert run.output_format is OutputFormat.xbrl_csv
    names = _package(db_session, run.id).namelist()
    assert any(n.endswith(".csv") for n in names)
    assert not any(n.endswith(".xbrl") for n in names)


def test_xml_format_generates_xbrl_instance(
    db_session: Session,
    ready_snapshot: TaxonomySnapshot,
    lcr_workflow: WorkflowConfig,
    entity: Entity,
    demo_fact_xlsx: bytes,
) -> None:
    # Pin this (regulator, workflow) to xBRL-XML.
    service.set_workflow_format_override(
        db_session,
        regulator_id=ready_snapshot.regulator_id,
        workflow_id=lcr_workflow.id,
        output_format=OutputFormat.xbrl_xml,
    )

    run = _run(db_session, ready_snapshot, lcr_workflow, entity)
    service.attach_fact_file(
        db_session, run_id=run.id, filename="facts.xlsx", data=demo_fact_xlsx
    )
    run = service.execute_run(db_session, run.id)
    assert run.status is RunStatus.generated, run.error
    assert run.output_format is OutputFormat.xbrl_xml

    zf = _package(db_session, run.id)
    xbrl_name = next(n for n in zf.namelist() if n.endswith(".xbrl"))
    assert not any(n.endswith(".csv") for n in zf.namelist())
    doc = zf.read(xbrl_name).decode("utf-8")

    # It parses, is an xbrli:xbrl instance, and carries the dimensional metric
    # facts assembled from the DPM (eba_met:mi900 monetary + mi901 percentage).
    root = ET.fromstring(doc)
    assert root.tag == "{http://www.xbrl.org/2003/instance}xbrl"
    assert "eba_met:mi900" in doc
    met_ns = "http://www.eba.europa.eu/xbrl/crr/dict/met"
    facts = [e for e in root if e.tag.startswith(f"{{{met_ns}}}")]
    assert len(facts) == 2
    # A dimensional scenario was emitted (datapoint 900 has dimensions).
    assert "xbrldi:explicitMember" in doc
