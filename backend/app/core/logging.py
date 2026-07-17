"""Structured logging setup.

Logs are emitted as single-line JSON so they aggregate cleanly in hosting.
Once a run starts, the run id is attached to every log line (see ``workflows/``
in later work); this module only configures the base handler.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from app.core.config import get_settings


class JsonFormatter(logging.Formatter):
    """Render log records as compact JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(
                record.created, tz=UTC
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Anything attached via ``logger.info(..., extra={"run_id": ...})``.
        if run_id := getattr(record, "run_id", None):
            payload["run_id"] = run_id
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging() -> None:
    """Install the JSON handler on the root logger. Idempotent."""
    settings = get_settings()
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())

    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
