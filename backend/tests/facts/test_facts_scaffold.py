"""Scaffold import checks for the facts stage.

No business logic yet — this only proves the package's modules import and the
router is wired, so the mirror stays honest as the stage grows.
"""

from __future__ import annotations

from fastapi import APIRouter


def test_facts_modules_import() -> None:
    from app.facts import models, router, schemas, service  # noqa: F401

    assert isinstance(router.router, APIRouter)
