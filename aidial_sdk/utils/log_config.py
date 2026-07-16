import os

from aidial_sdk._pydantic._compat import BaseModel
from aidial_sdk.utils.env import env_json_dict

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


def _default_formatter() -> dict:
    datefmt = "%Y-%m-%d %H:%M:%S"
    if _DIAL_SDK_LOG_FORMAT == "json":
        return {
            "()": "aidial_sdk.utils.json_log_formatter.JsonLogFormatter",
            "template": _DIAL_SDK_JSON_LOG_FORMAT,
            "datefmt": datefmt,
        }
    return {
        "()": "uvicorn.logging.DefaultFormatter",
        "fmt": _DIAL_SDK_TEXT_LOG_FORMAT,
        "datefmt": datefmt,
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
