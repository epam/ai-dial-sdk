import os

from aidial_sdk._pydantic._compat import BaseModel

DIAL_SDK_LOG = os.environ.get("DIAL_SDK_LOG", "WARNING").upper()


class LogConfig(BaseModel):
    """Logging configuration to be set for the server"""

    version: int = 1
    disable_existing_loggers: bool = False
    formatters: dict = {
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": "%(levelprefix)s | %(asctime)s | %(name)s | %(process)d | %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
            "use_colors": True,
        },
    }
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
