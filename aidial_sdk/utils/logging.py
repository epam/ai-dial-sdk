import logging
from contextvars import ContextVar

logger = logging.getLogger("aidial_sdk")

deployment_id: ContextVar[str | None] = ContextVar(
    "deployment_id", default=None
)


def set_log_deployment(new_deployment_id: str):
    deployment_id.set(new_deployment_id)


def reset_log_context() -> None:
    """Forgets a deployment inherited from an earlier request.

    A request's task can start with the ``contextvars`` of an earlier request
    on the same connection, so `DIALApp.__call__` calls this at the ASGI entry
    point. See `aidial_sdk.telemetry._context.reset_trace_context`.
    """
    deployment_id.set(None)


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
