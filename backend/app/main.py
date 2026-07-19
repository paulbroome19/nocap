"""FastAPI application entrypoint.

Wires the stage routers and the health endpoint. `workflows` is the only
package that orchestrates; this module only assembles the HTTP surface.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

from app.comparison.router import router as comparison_router
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.facts.router import get_template_normalizer
from app.facts.router import router as facts_router
from app.generation.router import router as generation_router
from app.taxonomy import service as taxonomy_service
from app.taxonomy.router import router as taxonomy_router
from app.taxonomy.service import normalize_template_code
from app.validation.router import router as validation_router
from app.workflows.router import router as workflows_router

logger = logging.getLogger(__name__)


class _SPAStaticFiles(StaticFiles):
    """Static files with single-page-app fallback.

    Serves built assets normally; for any path that doesn't map to a file (a
    client-side route like ``/releases/5`` opened directly or refreshed) it
    returns ``index.html`` so the router can take over. Real missing assets
    (e.g. a stale ``/assets/*.js``) still 404.
    """

    async def get_response(self, path: str, scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            # A missing file: for a client-side route (anything but a real asset)
            # serve index.html so the SPA router can render it. A genuinely
            # missing asset still 404s.
            if exc.status_code == 404 and not path.startswith("assets/"):
                return await super().get_response("index.html", scope)
            raise


def _mount_frontend(app: FastAPI, static_dir) -> None:
    """Serve the built SPA at ``/`` when a build is present (skipped in dev).

    Mounted after the API routers so ``/api/*`` and ``/health`` win; everything
    else falls through to the static build with SPA fallback.
    """
    index = static_dir / "index.html"
    if not index.is_file():
        logger.info("no frontend build at %s; static serving disabled", static_dir)
        return
    app.mount(
        "/", _SPAStaticFiles(directory=str(static_dir), html=True), name="spa"
    )
    logger.info("serving frontend build from %s", static_dir)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup guards, then reconcile snapshot status with on-disk artifacts.

    First a fail-fast schema check: if the database isn't at the migration head,
    refuse to start (clear message beats per-request 500s on a missing column).
    Then reconcile a stale ``ready`` snapshot to ``artifacts_missing``. Both read
    settings fresh so tests can disable them; the reconcile is best-effort, but
    the schema check is deliberately allowed to abort startup."""
    settings = get_settings()
    if settings.check_schema_on_startup:
        from app.core.db import engine
        from app.core.schema import check_schema_current

        check_schema_current(engine)  # raises → fail fast, do not serve
    if settings.reconcile_snapshots_on_startup:
        try:
            with SessionLocal() as db:
                # Self-heal releases stranded mid-creation by a killed container
                # (the residue that otherwise blocks re-uploading the same DPM),
                # then reconcile ready snapshots against what's on disk.
                cleared = taxonomy_service.clear_incomplete_creations(db)
                changed = taxonomy_service.verify_all_snapshots(db)
            if cleared:
                logger.warning(
                    "startup: cleared %d incomplete release(s) stranded "
                    "mid-creation", cleared,
                )
            if changed:
                logger.warning("startup: reconciled %d snapshot(s) with disk", changed)
        except Exception:  # noqa: BLE001 — never block startup on this
            logger.exception("startup snapshot reconciliation skipped")
    yield


def create_app() -> FastAPI:
    """Application factory."""
    configure_logging()
    settings = get_settings()

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=_lifespan)
    register_exception_handlers(app)

    # Composition root: wire the taxonomy contract's template-code normaliser
    # (canonical DB form) into the facts stage. Stages never import each other;
    # this cross-stage dependency lives here in the app assembly.
    app.dependency_overrides[get_template_normalizer] = lambda: (
        lambda code: normalize_template_code(code, form="db")
    )

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        """Liveness probe. Intentionally does not touch the database."""
        return {"status": "ok", "app": settings.app_name, "version": "0.1.0"}

    # Stage routers. Each is an empty APIRouter in this scaffold; wiring the
    # seams now keeps the architecture visible.
    app.include_router(taxonomy_router, prefix="/api/taxonomy", tags=["taxonomy"])
    app.include_router(facts_router, prefix="/api/facts", tags=["facts"])
    app.include_router(
        generation_router, prefix="/api/generation", tags=["generation"]
    )
    app.include_router(
        validation_router, prefix="/api/validation", tags=["validation"]
    )
    app.include_router(
        comparison_router, prefix="/api/comparison", tags=["comparison"]
    )
    app.include_router(
        workflows_router, prefix="/api/workflows", tags=["workflows"]
    )

    # Serve the built frontend last so the API surface takes precedence.
    _mount_frontend(app, settings.static_dir)

    return app


app = create_app()
