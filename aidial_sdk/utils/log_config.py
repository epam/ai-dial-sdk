import logging
import os
import sys
from typing import Literal

from uvicorn.logging import DefaultFormatter

from aidial_sdk.utils._json_log_formatter import JsonLogFormatter
from aidial_sdk.utils.env import env_json_dict

_DATEFMT = "%Y-%m-%d %H:%M:%S"

_DEFAULT_TEXT_FORMAT = (
    "%(levelprefix)s | %(asctime)s | %(name)s | %(process)d | %(message)s"
)
_DEFAULT_JSON_FORMAT = {
    "level": "%(levelname)s",
    "time": "%(asctime)s",
    "logger": "%(name)s",
    "process": "%(process)d",
    "message": "%(message)s",
}


class LogConfig:
    level: str
    formatter: logging.Formatter

    def __init__(
        self,
        *,
        level: str | None = None,
        log_format: Literal["text", "json"] | None = None,
        text_format: str | None = None,
        json_format: dict | None = None,
    ) -> None:
        self.level = (
            level or os.environ.get("DIAL_SDK_LOG", "WARNING")
        ).upper()
        resolved_format = (
            log_format or os.environ.get("DIAL_SDK_LOG_FORMAT", "text")
        ).lower()

        if resolved_format == "json":
            json_format = json_format or env_json_dict(
                "DIAL_SDK_JSON_LOG_FORMAT", _DEFAULT_JSON_FORMAT
            )
            self.formatter = JsonLogFormatter(
                template=json_format, datefmt=_DATEFMT
            )
        else:
            text_format = text_format or os.getenv(
                "DIAL_SDK_TEXT_LOG_FORMAT", _DEFAULT_TEXT_FORMAT
            )
            self.formatter = DefaultFormatter(
                fmt=text_format, datefmt=_DATEFMT, use_colors=True
            )


def configure_root_logger(config: LogConfig | None = None) -> None:
    """Route all logging through a single console handler on the root logger,
    using the SDK's format, so the application's own loggers get it too. Pass a
    ``LogConfig`` to override the ``DIAL_SDK_LOG*`` env vars.

    Idempotent; call once at startup, after ``DIALApp()``/telemetry init. Sets
    the ``aidial_sdk`` logger to ``config.level`` but leaves the root and uvicorn
    levels untouched — set your own loggers' levels yourself. If root already has
    a stderr console handler this function did not install (e.g. OTEL's via
    ``OTEL_PYTHON_LOG_CORRELATION``), it defers to it.
    """
    config = config or LogConfig()
    root = logging.getLogger()

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
        handler.setFormatter(config.formatter)
        setattr(handler, _MARKER, True)
        root.addHandler(handler)

    for name in ("aidial_sdk", "uvicorn", "uvicorn.access", "uvicorn.error"):
        child = logging.getLogger(name)
        child.handlers = []
        child.propagate = True

    logging.getLogger("aidial_sdk").setLevel(config.level)


def configure_sdk_logger() -> None:
    """Configure only the SDK's own loggers (``aidial_sdk``, ``uvicorn``), called
    once when ``DIALApp`` is imported. To format your own loggers the same way,
    call ``configure_root_logger()``."""
    config = LogConfig()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(config.formatter)

    aidial_sdk = logging.getLogger("aidial_sdk")
    aidial_sdk.handlers = [handler]
    aidial_sdk.setLevel(config.level)

    uvicorn = logging.getLogger("uvicorn")
    uvicorn.handlers = [handler]
    uvicorn.propagate = False
