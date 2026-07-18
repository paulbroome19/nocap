"""Business logic for the taxonomy stage.

Three concerns, all plain Python (no HTTP):

1. **Ingestion** — register an uploaded EBA DPM Access (``.accdb``) release,
   store it byte-for-byte, convert the needed tables to a per-snapshot SQLite
   file, validate it, and advance the snapshot's status.
2. **Registry** — list / fetch snapshots.
3. **Lookup** — the contract other stages get (via ``workflows``): resolve a
   (template, row, column) triple to a datapoint + datatype, list a module's
   templates, and normalise template codes.

See docs/dpm-notes.md for the DPM 2.0 schema this maps onto. Per the dependency
rules this imports only from ``app.core``.
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import SessionLocal
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.taxonomy.models import SnapshotStatus, TaxonomySnapshot
from app.taxonomy.schemas import (
    DatapointResolution,
    ModuleMetadata,
    TemplateInfo,
)

logger = logging.getLogger(__name__)

# Files stored under each snapshot's data dir.
SOURCE_FILENAME = "source.accdb"
SQLITE_FILENAME = "dpm.sqlite"

# Tables projected from the Access release into the per-snapshot SQLite. The raw
# .accdb is kept byte-for-byte, so this set can grow later without re-uploading.
DPM_TABLES = [
    "Framework",
    "Module",
    "ModuleVersion",
    "ModuleVersionComposition",
    "TableVersion",
    "Header",
    "HeaderVersion",
    "Cell",
    "TableVersionCell",
    "Variable",
    "VariableVersion",
    "Property",
    "DataType",
    "Release",
]

# A converted snapshot must contain these (non-empty Release) to be a readable
# DPM database.
REQUIRED_TABLES = [
    "Release",
    "Framework",
    "TableVersion",
    "Cell",
    "TableVersionCell",
    "VariableVersion",
    "Property",
    "DataType",
]


# ---------------------------------------------------------------------------
# Template-code normalisation
# ---------------------------------------------------------------------------

# Three forms exist (see docs/dpm-notes.md §4):
#   upstream fact file : C_67_00     (all underscores)
#   DPM 2.0 DB / query : C_67.00     (underscore after letters, dot before minor)
#   EBA display / xBRL : C 67.00     (space after letters)
# We accept all three and canonicalise to the DB form.
_TEMPLATE_RE = re.compile(
    r"^\s*([A-Za-z]+)[ _](\d+)[._](\d+)((?:[._][A-Za-z0-9]+)*)\s*$"
)


_TABLE_VARIANT_RE = re.compile(r"\.[a-z]$")


def template_of(table_code: str) -> str:
    """The regulatory template code for a table code.

    EBA filing indicators are declared per *template* (e.g. ``C_73.00``); a
    template's table variants (``C_73.00.a`` total, ``C_73.00.w`` by-currency)
    collapse to that one indicator. Strips a trailing ``.<letter>`` variant;
    codes with none (``C_00.01``) are returned unchanged.
    """
    return _TABLE_VARIANT_RE.sub("", table_code)


def normalize_template_code(code: str, *, form: str = "db") -> str:
    """Normalise a template code to the DB (``C_67.00``) or EBA (``C 67.00``) form.

    Preserves leading zeros in the numeric parts (they are significant); accepts
    the upstream, DB, and EBA input forms; is case-insensitive on the letters.
    Raises ``ValueError`` if the code is unrecognisable.
    """
    if form not in ("db", "eba"):
        raise ValueError(f"unknown form: {form!r}")
    m = _TEMPLATE_RE.match(code)
    if m is None:
        raise ValueError(f"unrecognised template code: {code!r}")
    prefix, major, minor, rest = m.groups()
    suffixes = [p for p in re.split(r"[._]", rest) if p]
    sep = "_" if form == "db" else " "
    out = f"{prefix.upper()}{sep}{major}.{minor}"
    if suffixes:
        out += "." + ".".join(suffixes)
    return out


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------


def snapshot_dir(settings: Settings, snapshot_id: int) -> Path:
    return settings.snapshots_dir / str(snapshot_id)


def _source_path(settings: Settings, snapshot_id: int) -> Path:
    return snapshot_dir(settings, snapshot_id) / SOURCE_FILENAME


def _sqlite_path(settings: Settings, snapshot_id: int) -> Path:
    return snapshot_dir(settings, snapshot_id) / SQLITE_FILENAME


def snapshot_taxonomy_packages(
    settings: Settings, snapshot_id: int
) -> list[Path]:
    """The taxonomy package zips in a snapshot's artifact slot.

    Per the Arelle/version-pinning direction, the XBRL taxonomy package is a
    per-release artifact loaded per snapshot. Drop the release's package zip(s)
    into ``{snapshot_dir}/taxonomy/`` (the slot); formula validation uses them.
    """
    slot = snapshot_dir(settings, snapshot_id) / "taxonomy"
    if not slot.is_dir():
        return []
    return sorted(slot.glob("*.zip"))


def compute_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Access -> SQLite conversion (mdbtools)
# ---------------------------------------------------------------------------


class ConversionError(RuntimeError):
    """Raised when the .accdb cannot be read / converted."""


def _extract_creates(schema_sql: str, tables: list[str]) -> str:
    """Pull the ``CREATE TABLE`` blocks for ``tables`` out of mdb-schema output."""
    want = set(tables)
    blocks: list[str] = []
    current: list[str] | None = None
    name_re = re.compile(r"^CREATE TABLE `([^`]+)`")
    for line in schema_sql.splitlines():
        if current is None:
            m = name_re.match(line)
            if m and m.group(1) in want:
                current = [line]
        else:
            current.append(line)
            if line.strip() == ");":
                blocks.append("\n".join(current))
                current = None
    return "\n".join(blocks) + "\n"


def convert_accdb_to_sqlite(
    accdb: Path,
    out_sqlite: Path,
    *,
    settings: Settings,
    tables: list[str] = DPM_TABLES,
) -> None:
    """Convert the needed DPM tables from an Access file into a SQLite file.

    Uses mdbtools: ``mdb-schema`` for DDL and ``mdb-export -I sqlite`` for rows.
    """
    if out_sqlite.exists():
        out_sqlite.unlink()
    try:
        schema = subprocess.run(
            [settings.mdb_schema_bin, str(accdb), "sqlite"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except FileNotFoundError as exc:
        raise ConversionError(
            f"mdbtools not found ({settings.mdb_schema_bin}); install mdbtools"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise ConversionError(
            f"not a readable Access database: {exc.stderr}"
        ) from exc

    creates = _extract_creates(schema, tables)
    if "CREATE TABLE" not in creates:
        raise ConversionError("expected DPM tables not present in the file")

    conn = sqlite3.connect(out_sqlite)
    try:
        conn.executescript(creates)
        for table in tables:
            inserts = subprocess.run(
                [settings.mdb_export_bin, "-I", "sqlite", str(accdb), table],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            if inserts.strip():
                conn.executescript(inserts)
        conn.commit()
    finally:
        conn.close()


def validate_dpm_sqlite(sqlite_path: Path) -> None:
    """Probe a converted snapshot; raise ``ValidationError`` if it isn't DPM."""
    if not sqlite_path.exists():
        raise ValidationError("converted snapshot database is missing")
    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    try:
        names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        missing = [t for t in REQUIRED_TABLES if t not in names]
        if missing:
            raise ValidationError(
                f"file is not a DPM database (missing tables: {', '.join(missing)})"
            )
        if conn.execute("SELECT count(*) FROM Release").fetchone()[0] == 0:
            raise ValidationError("DPM database contains no releases")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Ingestion + registry
# ---------------------------------------------------------------------------


def register_snapshot(
    db: Session,
    *,
    file_bytes: bytes,
    filename: str,
    version_label: str,
    regulator_id: int | None = None,
    settings: Settings | None = None,
) -> TaxonomySnapshot:
    """Persist a new snapshot (status=ingesting) and store the uploaded file.

    Rejects a re-upload of identical bytes (duplicate checksum). ``regulator_id``
    defaults to the EBA — the platform's default taxonomy publisher.
    """
    settings = settings or get_settings()
    if not file_bytes:
        raise ValidationError("uploaded file is empty")

    if regulator_id is None:
        from app.taxonomy.seed import eba

        regulator_id = eba(db).id

    checksum = compute_checksum(file_bytes)
    existing = db.scalar(
        select(TaxonomySnapshot).where(TaxonomySnapshot.checksum == checksum)
    )
    if existing is not None:
        raise ConflictError(
            f"this DPM file was already uploaded (snapshot id={existing.id})"
        )

    snapshot = TaxonomySnapshot(
        regulator_id=regulator_id,
        version_label=version_label,
        original_filename=filename,
        checksum=checksum,
        status=SnapshotStatus.ingesting,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)

    directory = snapshot_dir(settings, snapshot.id)
    directory.mkdir(parents=True, exist_ok=True)
    _source_path(settings, snapshot.id).write_bytes(file_bytes)

    logger.info("registered snapshot id=%s checksum=%s", snapshot.id, checksum)
    return snapshot


def ingest_snapshot(
    db: Session,
    snapshot: TaxonomySnapshot,
    *,
    settings: Settings | None = None,
    converter=convert_accdb_to_sqlite,
) -> None:
    """Convert + validate a registered snapshot, advancing status to ready/failed.

    ``converter`` is injectable so ingestion can be tested without mdbtools.
    """
    settings = settings or get_settings()
    source = _source_path(settings, snapshot.id)
    target = _sqlite_path(settings, snapshot.id)
    try:
        if not source.exists():
            raise ValidationError("uploaded source file is missing")
        converter(source, target, settings=settings)
        validate_dpm_sqlite(target)
    except Exception as exc:  # noqa: BLE001 — record any failure on the snapshot
        snapshot.status = SnapshotStatus.failed
        snapshot.error = str(exc)[:2000]
        db.commit()
        logger.exception("ingestion failed for snapshot id=%s", snapshot.id)
        return

    snapshot.status = SnapshotStatus.ready
    snapshot.error = None
    db.commit()
    logger.info("snapshot id=%s ready", snapshot.id)


def ingest_snapshot_task(snapshot_id: int) -> None:
    """Background entrypoint: open a fresh session and ingest by id."""
    settings = get_settings()
    with SessionLocal() as db:
        snapshot = db.get(TaxonomySnapshot, snapshot_id)
        if snapshot is None:
            logger.warning("ingest task: snapshot id=%s not found", snapshot_id)
            return
        ingest_snapshot(db, snapshot, settings=settings)


def list_snapshots(db: Session) -> list[TaxonomySnapshot]:
    return list(
        db.scalars(select(TaxonomySnapshot).order_by(TaxonomySnapshot.id.desc()))
    )


def get_snapshot(db: Session, snapshot_id: int) -> TaxonomySnapshot:
    snapshot = db.get(TaxonomySnapshot, snapshot_id)
    if snapshot is None:
        raise NotFoundError(f"snapshot id={snapshot_id} not found")
    return snapshot


# ---------------------------------------------------------------------------
# Artifact integrity + recovery
# ---------------------------------------------------------------------------


def snapshot_artifacts_present(settings: Settings, snapshot_id: int) -> bool:
    """True if the snapshot's converted DPM SQLite exists at the storage root."""
    return _sqlite_path(settings, snapshot_id).exists()


def verify_snapshot(
    db: Session, snapshot: TaxonomySnapshot, *, settings: Settings | None = None
) -> TaxonomySnapshot:
    """Reconcile a snapshot's status with what is actually on disk.

    ``ready`` but the converted DB is missing → ``artifacts_missing`` (with a
    clear message). ``artifacts_missing`` but the DB is present again (e.g. the
    data dir was corrected) → back to ``ready``. Other statuses are untouched.
    """
    settings = settings or get_settings()
    present = snapshot_artifacts_present(settings, snapshot.id)
    if snapshot.status is SnapshotStatus.ready and not present:
        snapshot.status = SnapshotStatus.artifacts_missing
        snapshot.error = (
            "the converted database is missing at the configured storage root; "
            "re-ingest from the stored original to recover"
        )
        db.commit()
        logger.warning("snapshot id=%s artifacts missing on disk", snapshot.id)
    elif snapshot.status is SnapshotStatus.artifacts_missing and present:
        snapshot.status = SnapshotStatus.ready
        snapshot.error = None
        db.commit()
        logger.info("snapshot id=%s artifacts recovered; back to ready", snapshot.id)
    return snapshot


def verify_all_snapshots(db: Session, *, settings: Settings | None = None) -> int:
    """Reconcile every ready/artifacts_missing snapshot. Returns count changed."""
    settings = settings or get_settings()
    changed = 0
    stmt = select(TaxonomySnapshot).where(
        TaxonomySnapshot.status.in_(
            [SnapshotStatus.ready, SnapshotStatus.artifacts_missing]
        )
    )
    for snapshot in db.scalars(stmt):
        before = snapshot.status
        verify_snapshot(db, snapshot, settings=settings)
        if snapshot.status is not before:
            changed += 1
    return changed


def reingest_snapshot(
    db: Session, snapshot_id: int, *, settings: Settings | None = None
) -> TaxonomySnapshot:
    """Rebuild the converted DB from the stored original — no re-upload.

    Reuses the ``source.accdb`` already on disk, so it bypasses the upload path
    and its checksum de-duplication entirely. Sets status to ``ingesting``; the
    caller schedules the conversion (see ``ingest_snapshot_task``).
    """
    settings = settings or get_settings()
    snapshot = get_snapshot(db, snapshot_id)
    if not _source_path(settings, snapshot.id).exists():
        raise ValidationError(
            f"cannot re-ingest snapshot id={snapshot.id}: its original file is "
            "not on disk at the configured storage root — re-upload it instead"
        )
    snapshot.status = SnapshotStatus.ingesting
    snapshot.error = None
    db.commit()
    logger.info("re-ingesting snapshot id=%s from stored original", snapshot.id)
    return snapshot


# ---------------------------------------------------------------------------
# Lookup — the contract other stages consume via workflows
# ---------------------------------------------------------------------------

_RELEASE_VALID = (
    "{a}.StartReleaseID <= :rid "
    "AND ({a}.EndReleaseID IS NULL OR {a}.EndReleaseID > :rid)"
)

_RESOLVE_SQL = f"""
SELECT tv.Code, ry.Code, cx.Code, vv.VariableID,
       dt.Code, dt.Name, p.PeriodType, tvc.CellCode
FROM TableVersion tv
JOIN Cell c   ON c.TableID = tv.TableID
JOIN Header hr ON hr.HeaderID = c.RowID    AND hr.Direction = 'Y'
JOIN Header hc ON hc.HeaderID = c.ColumnID AND hc.Direction = 'X'
JOIN HeaderVersion ry ON ry.HeaderID = c.RowID    AND ry.Code = :row
     AND {_RELEASE_VALID.format(a="ry")}
JOIN HeaderVersion cx ON cx.HeaderID = c.ColumnID AND cx.Code = :col
     AND {_RELEASE_VALID.format(a="cx")}
JOIN TableVersionCell tvc ON tvc.TableVID = tv.TableVID AND tvc.CellID = c.CellID
JOIN VariableVersion vv ON vv.VariableVID = tvc.VariableVID
JOIN Property p  ON p.PropertyID = vv.PropertyID
JOIN DataType dt ON dt.DataTypeID = p.DataTypeID
WHERE tv.Code = :tmpl AND {_RELEASE_VALID.format(a="tv")}
ORDER BY c.CellID
LIMIT 1
"""

_LIST_TEMPLATES_SQL = f"""
SELECT DISTINCT tv.Code, tv.Name
FROM ModuleVersion mv
JOIN ModuleVersionComposition mvc ON mvc.ModuleVID = mv.ModuleVID
JOIN TableVersion tv ON tv.TableVID = mvc.TableVID
WHERE mv.Code = :module
  AND {_RELEASE_VALID.format(a="mv")}
  AND {_RELEASE_VALID.format(a="tv")}
ORDER BY tv.Code
"""

_MODULE_META_SQL = f"""
SELECT mv.Code, f.Code, mv.VersionNumber, mv.Name
FROM ModuleVersion mv
JOIN Module m ON m.ModuleID = mv.ModuleID
JOIN Framework f ON f.FrameworkID = m.FrameworkID
WHERE mv.Code = :module AND {_RELEASE_VALID.format(a="mv")}
LIMIT 1
"""

# Templates in a module that the DPM marks as open/keyed (TableVersion.KeyID set).
# v1 generates closed tables only; open tables are guarded out.
_OPEN_TEMPLATES_SQL = f"""
SELECT DISTINCT tv.Code
FROM ModuleVersion mv
JOIN ModuleVersionComposition mvc ON mvc.ModuleVID = mv.ModuleVID
JOIN TableVersion tv ON tv.TableVID = mvc.TableVID
WHERE mv.Code = :module AND tv.KeyID IS NOT NULL
  AND {_RELEASE_VALID.format(a="mv")}
  AND {_RELEASE_VALID.format(a="tv")}
"""


class TaxonomyLookup:
    """Read-only queries against one snapshot's converted DPM SQLite file.

    Bind once per snapshot; reuse across lookups. Not thread-safe (one sqlite
    connection). Call ``close()`` (or use as a context manager) when done.
    """

    def __init__(self, sqlite_path: Path) -> None:
        self._conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)

    def __enter__(self) -> TaxonomyLookup:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    def default_release_id(self) -> int:
        """The current release (``IsCurrent``), else the highest release id."""
        row = self._conn.execute(
            "SELECT ReleaseID FROM Release WHERE IsCurrent <> 0 "
            "ORDER BY ReleaseID DESC LIMIT 1"
        ).fetchone()
        if row is not None:
            return int(row[0])
        row = self._conn.execute("SELECT max(ReleaseID) FROM Release").fetchone()
        if row is None or row[0] is None:
            raise ValidationError("snapshot has no releases")
        return int(row[0])

    def resolve(
        self,
        template_code: str,
        row_code: str,
        column_code: str,
        *,
        release_id: int | None = None,
    ) -> DatapointResolution | None:
        """Resolve a (template, row, column) triple to a datapoint + datatype.

        Returns ``None`` when the triple does not resolve (unknown template, or
        an unreported/void cell). Row/column codes are matched as text so
        leading zeros are significant (``"0010"`` != ``"10"``).
        """
        rid = release_id if release_id is not None else self.default_release_id()
        try:
            tmpl = normalize_template_code(template_code, form="db")
        except ValueError:
            return None
        params = {
            "tmpl": tmpl,
            "row": str(row_code),
            "col": str(column_code),
            "rid": rid,
        }
        row = self._conn.execute(_RESOLVE_SQL, params).fetchone()
        if row is None:
            return None
        return DatapointResolution(
            template_code=row[0],
            row_code=row[1],
            column_code=row[2],
            datapoint_id=int(row[3]),
            datatype_code=row[4],
            datatype_name=row[5],
            period_type=row[6],
            cell_code=row[7],
        )

    def list_templates(
        self, module_code: str, *, release_id: int | None = None
    ) -> list[TemplateInfo]:
        """List the templates (table versions) composing a module."""
        rid = release_id if release_id is not None else self.default_release_id()
        rows = self._conn.execute(
            _LIST_TEMPLATES_SQL, {"module": module_code, "rid": rid}
        ).fetchall()
        return [TemplateInfo(code=r[0], name=r[1]) for r in rows]

    def open_templates(
        self, module_code: str, *, release_id: int | None = None
    ) -> set[str]:
        """Template codes in the module the DPM marks as open/keyed."""
        rid = release_id if release_id is not None else self.default_release_id()
        rows = self._conn.execute(
            _OPEN_TEMPLATES_SQL, {"module": module_code, "rid": rid}
        ).fetchall()
        return {r[0] for r in rows}

    def module_metadata(
        self, module_code: str, *, release_id: int | None = None
    ) -> ModuleMetadata | None:
        """Framework + version identity of a module, for package generation."""
        rid = release_id if release_id is not None else self.default_release_id()
        row = self._conn.execute(
            _MODULE_META_SQL, {"module": module_code, "rid": rid}
        ).fetchone()
        if row is None:
            return None
        return ModuleMetadata(
            module_code=row[0],
            framework_code=row[1],
            module_version=row[2],
            name=row[3],
        )

    def release_code(self, release_id: int) -> str | None:
        """The release's code (e.g. "4.2") — used as the taxonomy version."""
        row = self._conn.execute(
            "SELECT Code FROM Release WHERE ReleaseID = ?", (release_id,)
        ).fetchone()
        return None if row is None else str(row[0])


def open_lookup(
    snapshot: TaxonomySnapshot, *, settings: Settings | None = None
) -> TaxonomyLookup:
    """Open a lookup for a ready snapshot. Callers own closing it."""
    settings = settings or get_settings()
    if snapshot.status is SnapshotStatus.artifacts_missing:
        raise ValidationError(
            f"snapshot id={snapshot.id} artifacts are missing on disk — "
            "re-ingest the snapshot to recover"
        )
    if snapshot.status is not SnapshotStatus.ready:
        raise ValidationError(
            f"snapshot id={snapshot.id} is not ready "
            f"(status={snapshot.status.value})"
        )
    path = _sqlite_path(settings, snapshot.id)
    if not path.exists():
        raise NotFoundError(
            f"snapshot id={snapshot.id} converted database is missing at the "
            "storage root — re-ingest the snapshot to recover"
        )
    return TaxonomyLookup(path)


def remove_snapshot_dir(settings: Settings, snapshot_id: int) -> None:
    """Purge a snapshot's on-disk artifacts. Snapshot rows are never deleted."""
    shutil.rmtree(snapshot_dir(settings, snapshot_id), ignore_errors=True)
