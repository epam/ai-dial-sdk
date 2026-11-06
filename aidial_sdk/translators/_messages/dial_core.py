import os
from collections.abc import Awaitable, Callable
from typing import TypeVar

from fastapi import Request

from aidial_sdk._errors import INTERNAL_ERROR_MESSAGE
from aidial_sdk.exceptions import InternalServerError
from aidial_sdk.utils.logging import logger as log

ClientT = TypeVar("ClientT")
ClientFactory = Callable[[Request], Awaitable[ClientT]] | ClientT

# The headers of the inbound request that DIAL Core reads when the translator
# calls it back. Any other header is not forwarded.
_FORWARDED_HEADERS = {
    # Core's per-request key
    "api-key",
    # Prompt caching policy of the request
    "x-dial-cache-policy",
    # Pins the request to the same upstream
    "x-upstream-id",
}


def forwarded_headers(request: Request) -> dict[str, str]:
    return {
        name: value
        for name, value in request.headers.items()
        if name.lower() in _FORWARDED_HEADERS
    }


def get_dial_url() -> str:
    url = os.getenv("DIAL_URL")
    if not url:
        log.error("DIAL_URL environment variable isn't set")
        raise InternalServerError(INTERNAL_ERROR_MESSAGE)

    return url.rstrip("/")
