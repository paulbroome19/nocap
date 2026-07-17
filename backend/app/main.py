"""FastAPI application entrypoint.

Wires the stage routers and the health endpoint. `workflows` is the only
package that orchestrates; this module only assembles the HTTP surface.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.comparison.router import router as comparison_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.facts.router import get_template_normalizer
from app.facts.router import router as facts_router
from app.generation.router import router as generation_router
from app.taxonomy.router import router as taxonomy_router
from app.taxonomy.service import normalize_template_code
from app.validation.router import router as validation_router
from app.workflows.router import router as workflows_router


def create_app() -> FastAPI:
    """Application factory."""
    configure_logging()
    settings = get_settings()

    app = FastAPI(title=settings.app_name, version="0.1.0")
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

    return app


app = create_app()
