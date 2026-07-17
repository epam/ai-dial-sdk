from aidial_sdk.utils.logging import logger

_LOGGING_DOC = (
    "https://github.com/epam/ai-dial-sdk/blob/development/docs/logging.md"
)


def warn_otel_log_correlation() -> None:
    logger.warning(
        "OTEL_PYTHON_LOG_CORRELATION=true is not the recommended way to add "
        "trace context to console logs: it double-logs SDK records and cannot "
        "produce JSON. Use DIAL_SDK_TEXT_LOG_FORMAT (with otel* placeholders) "
        f"instead — see {_LOGGING_DOC}."
    )
