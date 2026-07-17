"""Scaffold import checks for the validation stage.

No business logic yet — this only proves the package's modules import and the
router is wired, so the mirror stays honest as the stage grows.
"""

from __future__ import annotations

from fastapi import APIRouter


def test_validation_modules_import() -> None:
    from app.validation import models, router, schemas, service  # noqa: F401

    assert isinstance(router.router, APIRouter)
