from urllib.parse import quote

from fastapi import Request
from openai import AsyncOpenAI, Omit, omit

from aidial_sdk.translators.messages_to_chat_completions.bedrock import (
    get_anthropic_http_client,
)
from aidial_sdk.translators.messages_to_chat_completions.settings import (
    get_dial_api_version,
)

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


def _client(
    base_url: str, default_query: dict[str, str] | None = None
) -> AsyncOpenAI:
    return AsyncOpenAI(
        # Required by the SDK; Core authenticates the forwarded `api-key` header.
        api_key="-",
        base_url=base_url,
        default_query=default_query,
        max_retries=0,
        http_client=get_anthropic_http_client(),
    )


def core_v1_client(dial_url: str) -> AsyncOpenAI:
    return _client(f"{dial_url}/openai/v1")


def core_legacy_client(dial_url: str, deployment: str) -> AsyncOpenAI:
    return _client(
        f"{dial_url}/openai/deployments/{quote(deployment, safe='')}",
        {"api-version": get_dial_api_version()},
    )


def core_headers(request: Request) -> dict[str, str | Omit]:
    # Without the override the SDK sends `Authorization: Bearer -`
    headers: dict[str, str | Omit] = {"Authorization": omit}
    headers.update(
        {
            name: value
            for name, value in request.headers.items()
            if name.lower() in _FORWARDED_HEADERS
        }
    )
    return headers
