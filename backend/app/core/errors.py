"""Application error types and FastAPI exception handlers.

Stage services raise these plain-Python errors; they do not know HTTP exists.
The handlers here translate them into responses at the edge.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base class for expected, domain-level failures.

    ``status_code`` lets a service signal intent (not found, invalid input)
    without importing FastAPI.
    """

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "app_error"

    def __init__(self, message: str, *, details: list | None = None) -> None:
        super().__init__(message)
        self.message = message
        # Optional structured payload (e.g. per-row rejection messages).
        self.details = details


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ValidationError(AppError):
    status_code = 422  # Unprocessable Content
    code = "validation_error"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class ArtifactUnavailableError(AppError):
    """A known record's stored bytes are missing at the storage root.

    Distinct from ``NotFoundError`` (the record itself is unknown): the artifact
    existed but is gone from disk (e.g. the data dir moved). 410 Gone so clients
    can tell "was here, now missing" from "never existed".
    """

    status_code = status.HTTP_410_GONE
    code = "artifact_unavailable"


class FileRejectedError(AppError):
    """An uploaded file failed shape validation. ``details`` lists row errors."""

    status_code = 422  # Unprocessable Content
    code = "file_rejected"


def register_exception_handlers(app: FastAPI) -> None:
    """Wire ``AppError`` translation into the FastAPI app."""

    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        error: dict[str, object] = {"code": exc.code, "message": exc.message}
        if exc.details is not None:
            error["details"] = exc.details
        return JSONResponse(status_code=exc.status_code, content={"error": error})
