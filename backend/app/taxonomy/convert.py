"""Convert an EBA DPM 2.0 Access database to the compact query SQLite — locally.

Use this when the EBA DPM 2.0 download (a ~720 MB Microsoft Access ``.accdb``
file) is too large to upload through the web app. Run it on your own computer to
produce a compact ``dpm.sqlite`` (~80 MB), then upload *that* file into the DPM
database slot of the release wizard. The output is exactly the query database
the server would have built, so the release behaves identically either way.

Prerequisite: mdbtools must be installed
    macOS:  brew install mdbtools
    Ubuntu: sudo apt-get install -y mdbtools

Usage (from the ``backend`` directory, with the virtualenv active):
    python -m app.taxonomy.convert "DPM_Database_2.0.accdb" dpm.sqlite

No database connection or configuration is required — this only shells out to
mdbtools and writes the SQLite file.
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.core.config import get_settings
from app.taxonomy.service import (
    ConversionError,
    convert_accdb_to_sqlite,
    validate_dpm_sqlite,
)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2:
        print(
            "usage: python -m app.taxonomy.convert "
            "<input.accdb> <output.sqlite>",
            file=sys.stderr,
        )
        return 2
    src, out = Path(argv[0]), Path(argv[1])
    if not src.exists():
        print(f"error: input file not found: {src}", file=sys.stderr)
        return 1
    try:
        print(f"converting {src.name} → {out} (this can take a minute)…")
        convert_accdb_to_sqlite(src, out, settings=get_settings())
        validate_dpm_sqlite(out)
    except ConversionError as exc:
        print(f"conversion failed: {exc}", file=sys.stderr)
        return 1
    size_mb = out.stat().st_size / 1_000_000
    print(
        f"done: wrote {out} ({size_mb:.0f} MB). "
        "Upload this file as the DPM database in the release wizard."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
