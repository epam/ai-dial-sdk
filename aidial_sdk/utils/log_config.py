import logging
import os
import sys

from uvicorn.logging import DefaultFormatter

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


def configure_sdk_logger() -> None:
    """Configure the SDK's own loggers. Called once when ``DIALApp`` is imported.

    It does **not** touch the root logger or your application's loggers. To give
    your own loggers the same formatting, call ``configure_root_logger()``.
    """
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(build_formatter())

    aidial_sdk = logging.getLogger("aidial_sdk")
    aidial_sdk.handlers = [handler]
    aidial_sdk.setLevel(DIAL_SDK_LOG)

    uvicorn = logging.getLogger("uvicorn")
    uvicorn.handlers = [handler]
    uvicorn.propagate = False
