import os

from aidial_sdk._errors import INTERNAL_ERROR_MESSAGE
from aidial_sdk.exceptions import InternalServerError
from aidial_sdk.utils.logging import logger as log


def get_dial_url() -> str:
    url = os.getenv("DIAL_URL")
    if not url:
        log.error("DIAL_URL environment variable isn't set")
        raise InternalServerError(INTERNAL_ERROR_MESSAGE)

    return url.rstrip("/")


def get_dial_api_version() -> str:
    return os.getenv("DIAL_API_VERSION") or "2025-01-01-preview"
