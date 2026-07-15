import os

from aidial_sdk._pydantic._compat import BaseModel

DIAL_SDK_LOG = os.environ.get("DIAL_SDK_LOG", "WARNING").upper()

# DIAL_SDK_LOG_FORMAT selects the console format ("text" or "json"). The two
# defaults carry the same fields. The per-format vars override the template.
# In the JSON template every string leaf is a %-format string (same grammar as
# the text one); see docs/logging.
DIAL_SDK_LOG_FORMAT = os.environ.get("DIAL_SDK_LOG_FORMAT", "text").lower()
DIAL_SDK_TEXT_LOG_FORMAT = os.environ.get(
    "DIAL_SDK_TEXT_LOG_FORMAT",
    "%(levelprefix)s | %(asctime)s | %(name)s | %(process)d | %(message)s",
)
DIAL_SDK_JSON_LOG_FORMAT = os.environ.get(
    "DIAL_SDK_JSON_LOG_FORMAT",
    '{"level": "%(levelname)s", "time": "%(asctime)s", "logger": "%(name)s",'
    ' "process": "%(process)d", "message": "%(message)s"}',
)


def _default_formatter() -> dict:
    if DIAL_SDK_LOG_FORMAT == "json":
        return {
            "()": "aidial_sdk.utils.json_log_formatter.JsonLogFormatter",
            "template": DIAL_SDK_JSON_LOG_FORMAT,
            "datefmt": "%Y-%m-%d %H:%M:%S",
        }
    return {
        "()": "uvicorn.logging.DefaultFormatter",
        "fmt": DIAL_SDK_TEXT_LOG_FORMAT,
        "datefmt": "%Y-%m-%d %H:%M:%S",
        "use_colors": True,
    }


class LogConfig(BaseModel):
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
