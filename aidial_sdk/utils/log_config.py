import logging
import os
import sys
from typing import Literal

from uvicorn.logging import DefaultFormatter

from aidial_sdk.utils._json_log_formatter import JsonLogFormatter
from aidial_sdk.utils._logging import remove_stream_handlers
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


_SDK_LOGGERS = ("aidial_sdk", "uvicorn", "uvicorn.access", "uvicorn.error")

_otel_owns_console = False


def set_otel_owns_console() -> None:
    global _otel_owns_console
    _otel_owns_console = True


def route_sdk_loggers_to_root() -> None:
    for name in _SDK_LOGGERS:
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True


def configure_root_logger(config: LogConfig | None = None) -> None:
    """Route all logging through a single console handler on the root logger,
    using the SDK's format, so the application's own loggers get it too. Pass a
    ``LogConfig`` to override the ``DIAL_SDK_LOG*`` env vars.
    """

    config = config or LogConfig()
    root = logging.getLogger()

    # Defer the root console handler to OTel when it owns it;
    # otherwise, install our own and drop competing stderr handlers
    if not _otel_owns_console:
        # Remove any competing handlers to avoid duplicate logging
        remove_stream_handlers(root, sys.stderr)
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(config.formatter)
        root.addHandler(handler)

    route_sdk_loggers_to_root()

    logging.getLogger("aidial_sdk").setLevel(config.level)


def configure_sdk_logger() -> None:
    """Configure only the SDK's own loggers (``aidial_sdk``, ``uvicorn``), called
    once when ``DIALApp`` is imported. To format your own loggers the same way,
    call ``configure_root_logger()``."""

    config = LogConfig()
    aidial_sdk = logging.getLogger("aidial_sdk")
    uvicorn = logging.getLogger("uvicorn")

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(config.formatter)
    aidial_sdk.handlers = [handler]
    uvicorn.handlers = [handler]
    uvicorn.propagate = False

    aidial_sdk.setLevel(config.level)
