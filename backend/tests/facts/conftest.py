"""Facts-stage test fixtures."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from app.taxonomy.service import normalize_template_code


@pytest.fixture
def normalize() -> Callable[[str], str]:
    """The taxonomy contract's normaliser (canonical DB form) — injected the
    same way the app composition root wires it into the facts stage."""
    return lambda code: normalize_template_code(code, form="db")
