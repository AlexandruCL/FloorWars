"""Structured JSON logging to stdout (plan section 7.8: shipped by Alloy to Loki).

Every record is one JSON object with at least ``timestamp``, ``level``, ``logger`` and
``message``. Uvicorn's loggers are routed through the same handler so access and error
logs share the format. Never pass secrets (tokens, passwords, connection strings) to a
logger; settings hold them as ``SecretStr`` for that reason.
"""

import logging
import logging.config
from typing import Any

from pythonjsonlogger.core import RESERVED_ATTRS
from pythonjsonlogger.json import JsonFormatter

UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")
# Uvicorn adds an ANSI-coloured duplicate of the message as ``color_message``; drop it.
DROPPED_ATTRS = ("color_message",)


def build_formatter() -> JsonFormatter:
    """Formatter producing ``{"timestamp", "level", "logger", "message", ...extra}``."""
    return JsonFormatter(
        "{levelname}{name}{message}",
        style="{",
        rename_fields={"levelname": "level", "name": "logger"},
        timestamp=True,
        reserved_attrs=[*RESERVED_ATTRS, *DROPPED_ATTRS],
    )


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON handler on the root logger and route uvicorn loggers to it."""
    config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"json": {"()": build_formatter}},
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "stream": "ext://sys.stdout",
            }
        },
        "root": {"level": level, "handlers": ["stdout"]},
        "loggers": {
            name: {"level": level, "handlers": [], "propagate": True} for name in UVICORN_LOGGERS
        },
    }
    logging.config.dictConfig(config)
