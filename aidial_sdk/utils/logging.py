import logging
from contextvars import ContextVar
from typing import Optional

logger = logging.getLogger("aidial_sdk")

deployment_id: ContextVar[Optional[str]] = ContextVar(
    "deployment_id", default=None
)


def set_log_deployment(new_deployment_id: str):
    deployment_id.set(new_deployment_id)


def log_info(message: str, *args, **kwargs):
    logger.info(f"[{deployment_id.get()}] {message}", *args, **kwargs)


def log_debug(message: str, *args, **kwargs):
    logger.debug(f"[{deployment_id.get()}] {message}", *args, **kwargs)


def log_warning(message: str, *args, **kwargs):
    logger.warning(f"[{deployment_id.get()}] {message}", *args, **kwargs)


def log_error(message: str, *args, **kwargs):
    logger.error(f"[{deployment_id.get()}] {message}", *args, **kwargs)


def log_exception(message: str, *args, **kwargs):
    logger.exception(message, *args, **kwargs)
