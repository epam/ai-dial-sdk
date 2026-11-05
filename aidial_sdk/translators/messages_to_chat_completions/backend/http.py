from collections.abc import AsyncGenerator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from urllib.parse import quote

import httpx
import openai
from fastapi import Request
from openai import AsyncOpenAI, AsyncStream, Omit, omit
from openai.types.chat import ChatCompletion, ChatCompletionChunk

from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.translators.messages_to_chat_completions.backend.client import (
    HEARTBEAT,
    Heartbeat,
)
from aidial_sdk.translators.messages_to_chat_completions.settings import (
    get_dial_api_version,
)
from aidial_sdk.utils.logging import logger as log
from aidial_sdk.utils.streaming import with_heartbeat

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
    base_url: str,
    http_client: httpx.AsyncClient,
    default_query: dict[str, str] | None = None,
) -> AsyncOpenAI:
    return AsyncOpenAI(
        # Required by the SDK; Core authenticates the forwarded `api-key` header.
        api_key="-",
        base_url=base_url,
        default_query=default_query,
        max_retries=0,
        http_client=http_client,
    )


def core_v1_client(
    dial_url: str, http_client: httpx.AsyncClient
) -> AsyncOpenAI:
    return _client(f"{dial_url}/openai/v1", http_client)


def core_legacy_client(
    dial_url: str, deployment: str, http_client: httpx.AsyncClient
) -> AsyncOpenAI:
    return _client(
        f"{dial_url}/openai/deployments/{quote(deployment, safe='')}",
        http_client,
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


# An error event in a stream has no status code, only a type or a code
_STREAM_ERROR_STATUS_CODES: dict[str | None, int] = {
    "invalid_request_error": 400,
    "rate_limit_exceeded": 429,
}


def _extract_error_message(e: openai.APIStatusError) -> str:
    body = e.body
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"]
        if isinstance(error, str) and error:
            return error
        if isinstance(body.get("message"), str):
            return body["message"]

    if isinstance(body, str) and body.strip():
        return body.strip()

    return e.message


def _from_core_error(e: openai.APIError) -> DIALException:
    match e:
        case openai.APIStatusError():
            return DIALException(
                _extract_error_message(e), status_code=e.status_code
            )
        case openai.APIConnectionError():
            log.error(f"Failed to reach DIAL Core: {e}")
            return DIALException("Failed to reach DIAL Core", status_code=502)
        case _:
            log.error(f"DIAL Core reported an error in the stream: {e}")
            status_code = (
                _STREAM_ERROR_STATUS_CODES.get(e.type)
                or _STREAM_ERROR_STATUS_CODES.get(e.code)
                or 500
            )
            return DIALException(e.message, status_code=status_code)


@contextmanager
def _core_errors() -> Iterator[None]:
    try:
        yield
    except openai.APIError as e:
        raise _from_core_error(e) from e


async def _with_heartbeat(
    stream: AsyncStream[ChatCompletionChunk], heartbeat_interval: float | None
) -> AsyncGenerator[ChatCompletionChunk | Heartbeat, None]:
    with _core_errors():
        async with stream:
            async for item in with_heartbeat(
                aiter(stream),
                heartbeat_interval=heartbeat_interval,
                heartbeat=HEARTBEAT,
            ):
                yield item


@dataclass
class ChatClientHttp:
    client: AsyncOpenAI
    core_headers: dict[str, str | Omit]
    heartbeat_interval: float | None

    async def create_stream(
        self, body: dict
    ) -> AsyncGenerator[ChatCompletionChunk | Heartbeat, None]:
        with _core_errors():
            stream = await self.client.post(
                "/chat/completions",
                cast_to=ChatCompletion,
                body=body,
                options={"headers": self.core_headers},
                stream=True,
                stream_cls=AsyncStream[ChatCompletionChunk],
            )
        return _with_heartbeat(stream, self.heartbeat_interval)

    async def create_block(self, body: dict) -> ChatCompletion:
        with _core_errors():
            response = await self.client.post(
                "/chat/completions",
                cast_to=ChatCompletion,
                body=body,
                options={"headers": self.core_headers},
            )
        return response
