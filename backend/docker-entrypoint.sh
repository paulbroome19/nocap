#!/usr/bin/env bash
# Container entrypoint: bring the schema to head, seed reference data, then
# serve. Runs from the backend source dir (WORKDIR). Migrations + seeds are
# idempotent, so this is safe on every boot of the single demo instance.
set -euo pipefail

# Ensure the storage root + Arelle config dir exist on the mounted volume.
mkdir -p "${DATA_DIR:-/data}" "${XDG_CONFIG_HOME:-/data/arelle}"

echo "[entrypoint] applying database migrations…"
alembic upgrade head

echo "[entrypoint] seeding reference data (idempotent)…"
python -m app.taxonomy.seed
python -m app.workflows.seed

echo "[entrypoint] starting uvicorn on port ${PORT:-8000}…"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
