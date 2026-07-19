# NoCap — single-service image: FastAPI (uvicorn) serves the API *and* the
# built React SPA as static files. One container, one volume, no CORS.
#
# Why one service (not two): the frontend already calls the API on relative
# ``/api`` paths, so same-origin serving removes CORS entirely; the app needs a
# single persistent volume (the DPM/taxonomy/run store) that only the backend
# touches; and a demo is simpler to operate as one deployable. A split (static
# CDN + API) buys nothing here and adds a cross-origin surface to configure.

# ---------------------------------------------------------------------------
# Stage 1 — build the frontend (Vite) into static assets.
# ---------------------------------------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build   # -> /build/dist

# ---------------------------------------------------------------------------
# Stage 2 — Python runtime.
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

# mdbtools: converts the EBA DPM Access (.accdb) release to SQLite on ingest.
# (Pre-converted-SQLite uploads skip this, but the .accdb path still needs it.)
RUN apt-get update \
    && apt-get install -y --no-install-recommends mdbtools \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app/backend

# Dependency layer (cached until pyproject.toml changes): install the Python
# dependencies against a stub package so a source edit doesn't reinstall the
# heavy deps (Arelle et al.).
COPY backend/pyproject.toml ./
RUN mkdir -p app && touch app/__init__.py \
    && pip install . \
    && rm -rf app

# Application source. We run uvicorn/alembic from this directory (WORKDIR), so
# imports resolve against this tree — the vendored eurofiling data files (not
# just .py) are therefore always present, regardless of setuptools packaging.
COPY backend/ ./

# The built SPA from stage 1.
COPY --from=frontend /build/dist /app/frontend/dist

# Storage + Arelle config live on the mounted volume (set DATA_DIR to it).
# XDG_CONFIG_HOME points Arelle's ~/.config/arelle at a writable, persistent
# path — without a writable HOME, Arelle aborts on startup even when offline.
ENV DATA_DIR=/data \
    STATIC_DIR=/app/frontend/dist \
    XDG_CONFIG_HOME=/data/arelle \
    ENVIRONMENT=production \
    ARELLE_ENABLED=true

COPY backend/docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/docker-entrypoint.sh"]
