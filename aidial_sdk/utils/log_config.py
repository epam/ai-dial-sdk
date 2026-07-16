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


def build_formatter() -> logging.Formatter:
    """The console formatter selected by ``DIAL_SDK_LOG_FORMAT`` (text or json)."""
    if _DIAL_SDK_LOG_FORMAT == "json":
        return JsonLogFormatter(
            template=_DIAL_SDK_JSON_LOG_FORMAT, datefmt=_DATEFMT
        )
    return DefaultFormatter(
        fmt=_DIAL_SDK_TEXT_LOG_FORMAT, datefmt=_DATEFMT, use_colors=True
    )


def configure_root_logger() -> None:
    """Route all logging through a single console handler on the root logger,
    using the SDK's env-selected format (``DIAL_SDK_LOG_FORMAT=text|json``).

    Call once at startup, after ``DIALApp()``/telemetry init. Clients get the
    SDK's formatting for their own loggers for free — they only need to set
    their loggers' levels.

    If root already has a stderr console handler that this function did not
    install — e.g. one OTEL added via ``OTEL_PYTHON_LOG_CORRELATION`` — it defers
    to it and does not add a second one.

    The root logger's level is left untouched (stdlib default ``WARNING``); set
    per-logger levels yourself for the loggers you care about.
    """
    root = logging.getLogger()

    # Drop the console handler we installed on a previous call ensuring idempotency
    _MARKER = "_aidial_sdk_console_handler"
    root.handlers = [h for h in root.handlers if not getattr(h, _MARKER, False)]

    # Defer to a stderr console handler already on root (e.g. OTEL's) rather
    # than adding a second one that would duplicate every line.
    has_console_handler = any(
        isinstance(h, logging.StreamHandler)
        and getattr(h, "stream", None) is sys.stderr
        for h in root.handlers
    )
    if not has_console_handler:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(build_formatter())
        setattr(handler, _MARKER, True)
        root.addHandler(handler)

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
