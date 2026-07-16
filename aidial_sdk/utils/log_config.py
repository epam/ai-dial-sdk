import logging
import logging.config
import os
import sys

from uvicorn.logging import DefaultFormatter

from aidial_sdk._pydantic._compat import BaseModel
from aidial_sdk.utils.env import env_json_dict
from aidial_sdk.utils.json_log_formatter import JsonLogFormatter

DIAL_SDK_LOG = os.environ.get("DIAL_SDK_LOG", "WARNING").upper()

_DIAL_SDK_LOG_FORMAT = os.environ.get("DIAL_SDK_LOG_FORMAT", "text").lower()
_DIAL_SDK_TEXT_LOG_FORMAT = os.environ.get(
    "DIAL_SDK_TEXT_LOG_FORMAT",
    "%(levelprefix)s | %(asctime)s | %(name)s | %(process)d | %(message)s",
)
_DIAL_SDK_JSON_LOG_FORMAT = env_json_dict(
    "DIAL_SDK_JSON_LOG_FORMAT",
    {
        "level": "%(levelname)s",
        "time": "%(asctime)s",
        "logger": "%(name)s",
        "process": "%(process)d",
        "message": "%(message)s",
    },
)

_DATEFMT = "%Y-%m-%d %H:%M:%S"

# Marks the console handler installed by configure_root_logger so repeat calls
# replace it instead of stacking duplicates (and leave other handlers alone).
_CONSOLE_HANDLER_MARKER = "_aidial_sdk_console_handler"


def build_formatter() -> logging.Formatter:
    """The console formatter selected by ``DIAL_SDK_LOG_FORMAT`` (text or json)."""
    if _DIAL_SDK_LOG_FORMAT == "json":
        return JsonLogFormatter(
            template=_DIAL_SDK_JSON_LOG_FORMAT, datefmt=_DATEFMT
        )
    return DefaultFormatter(
        fmt=_DIAL_SDK_TEXT_LOG_FORMAT, datefmt=_DATEFMT, use_colors=True
    )


def _default_formatter() -> dict:
    # dictConfig form of build_formatter(), referenced by import path so
    # LogConfig.model_dump() stays serializable.
    if _DIAL_SDK_LOG_FORMAT == "json":
        return {
            "()": "aidial_sdk.utils.json_log_formatter.JsonLogFormatter",
            "template": _DIAL_SDK_JSON_LOG_FORMAT,
            "datefmt": _DATEFMT,
        }
    return {
        "()": "uvicorn.logging.DefaultFormatter",
        "fmt": _DIAL_SDK_TEXT_LOG_FORMAT,
        "datefmt": _DATEFMT,
        "use_colors": True,
    }


def configure_root_logger(*, level: str | None = None) -> None:
    """Route all logging through a single console handler on the root logger,
    using the SDK's env-selected format (``DIAL_SDK_LOG_FORMAT=text|json``).

    Call once at startup, after ``DIALApp()``/telemetry init. Clients get the
    SDK's formatting for their own loggers for free — they only need to set
    their loggers' levels.

    Idempotent: replaces the console handler a previous call installed, and
    preserves any other root handlers (e.g. the OTLP export handler added by
    telemetry). Child SDK/uvicorn loggers are pointed at the root handler.

    ``level`` sets the root logger's level; when ``None`` the root level is left
    untouched (defaults to ``WARNING``). This does not silence loggers that set
    their own level — a record created by e.g. an ``INFO``-level ``app`` logger
    still reaches the root handler regardless of the root level; the root level
    only applies to loggers that don't set one of their own.
    """
    root = logging.getLogger()
    root.handlers = [
        h
        for h in root.handlers
        if not getattr(h, _CONSOLE_HANDLER_MARKER, False)
    ]

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(build_formatter())
    setattr(handler, _CONSOLE_HANDLER_MARKER, True)
    root.addHandler(handler)

    if level is not None:
        root.setLevel(level.upper())

    for name in ("aidial_sdk", "uvicorn", "uvicorn.access", "uvicorn.error"):
        child = logging.getLogger(name)
        child.handlers = []
        child.propagate = True


class _LogConfig(BaseModel):
    """Logging configuration to be set for the server"""

    version: int = 1
    disable_existing_loggers: bool = False
    formatters: dict = {"default": _default_formatter()}
    handlers: dict = {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
        },
    }
    loggers: dict = {
        "aidial_sdk": {"handlers": ["default"], "level": DIAL_SDK_LOG},
        "uvicorn": {
            "handlers": ["default"],
            "propagate": False,
        },
    }


def configure_sdk_logger() -> None:
    """Configure the SDK's own loggers. Called once when ``DIALApp`` is imported.

    By default it attaches a single stderr handler using the env-selected format
    (``build_formatter()`` — text or json per ``DIAL_SDK_LOG_FORMAT``) to the
    ``aidial_sdk`` and ``uvicorn`` loggers, sets ``aidial_sdk`` to ``DIAL_SDK_LOG``
    (default ``WARNING``), and stops ``uvicorn`` from propagating to the root
    logger (so uvicorn lines aren't duplicated by any root handler).

    It does **not** touch the root logger or your application's loggers. To give
    your own loggers the same formatting, call ``configure_root_logger()``.
    """
    logging.config.dictConfig(_LogConfig().model_dump())
