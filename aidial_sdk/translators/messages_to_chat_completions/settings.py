import os

from aidial_sdk.translators.messages_to_chat_completions.errors import (
    INTERNAL_ERROR_MESSAGE,
    AnthropicErrorType,
    AnthropicHTTPError,
)
from aidial_sdk.translators.messages_to_chat_completions.utils.log_config import (
    bedrock_logger as log,
)


def get_dial_url() -> str:
    url = os.getenv("DIAL_URL")
    if not url:
        log.error("translator is not configured (DIAL_URL is not set)")
        raise AnthropicHTTPError(AnthropicErrorType.API, INTERNAL_ERROR_MESSAGE)

    return url.rstrip("/")


def get_dial_api_version() -> str:
    return os.getenv("DIAL_API_VERSION") or "2025-01-01-preview"
