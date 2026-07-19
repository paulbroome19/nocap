"""The E1 data migration re-keys existing artifacts without breaking refs."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa

_MIG = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "d3a71c9e4f52_system_storage_keys_and_release_deletion.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_d3a71c9e4f52", _MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_rekey_moves_file_and_leaves_missing_alone(tmp_path: Path) -> None:
    mig = _load_migration()
    data_dir = tmp_path

    old_key = "runs/5/fact_input/Q4 facts.xlsx"  # old filename-based key
    p = data_dir / old_key
    p.parent.mkdir(parents=True)
    p.write_bytes(b"payload")
    missing_key = "runs/6/fact_input/gone.xlsx"  # row whose file is absent

    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text(
            "CREATE TABLE run_file (id INTEGER PRIMARY KEY, filename TEXT, "
            "storage_key TEXT)"
        ))
        conn.execute(
            sa.text("INSERT INTO run_file VALUES (1, 'Q4 facts.xlsx', :k)"),
            {"k": old_key},
        )
        conn.execute(
            sa.text("INSERT INTO run_file VALUES (2, 'gone.xlsx', :k)"),
            {"k": missing_key},
        )
        mig._rekey_table(conn, data_dir, "run_file")
        rows = dict(
            conn.execute(
                sa.text("SELECT id, storage_key FROM run_file")
            ).fetchall()
        )

    # Row 1 re-keyed to a system name in the same dir; file moved; reference OK.
    assert rows[1] != old_key
    assert rows[1].startswith("runs/5/fact_input/")
    assert rows[1].endswith(".xlsx")
    assert "facts" not in rows[1]
    assert not (data_dir / old_key).exists()
    assert (data_dir / rows[1]).read_bytes() == b"payload"

    # Row 2 (file missing) is left untouched — no fabricated reference.
    assert rows[2] == missing_key
