from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import contextmanager
from typing import TypeVar

import httpx
from fastapi import Request
from fastapi.responses import Response, StreamingResponse

from aidial_sdk._errors import Handler
from aidial_sdk.deployment.from_request_mixin import get_client_deployment_id
from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.translators.messages_to_chat_completions.backend.http import (
    forwarded_headers,
)
from aidial_sdk.translators.messages_to_chat_completions.settings import (
    get_dial_url,
)
from aidial_sdk.utils.logging import logger as log

ClientT = TypeVar("ClientT")
ClientFactory = Callable[[Request], Awaitable[ClientT]] | ClientT


def dial_core_handler(get_client: ClientFactory[httpx.AsyncClient]) -> Handler:
    """A Responses API handler that serves the request through DIAL Core."""

    async def _handler(request: Request) -> Response:
        http_client = (
            await get_client(request) if callable(get_client) else get_client
        )
        body = await request.json()
        # DIAL Core routes the Responses API by the model, while the model of
        # a request DIAL Core forwards is the overrideName of the deployment
        body["model"] = get_client_deployment_id(
            request.headers, body.get("model")
        )
        with _core_errors():
            response = await http_client.send(
                http_client.build_request(
                    "POST",
                    f"{get_dial_url()}/openai/v1/responses",
                    json=body,
                    headers=forwarded_headers(request),
                ),
                stream=True,
            )
        return StreamingResponse(
            _content(response), status_code=response.status_code
        )

    return _handler


async def _content(response: httpx.Response) -> AsyncIterator[bytes]:
    try:
        with _core_errors():
            async for chunk in response.aiter_bytes():
                yield chunk
    finally:
        await response.aclose()


@contextmanager
def _core_errors() -> Iterator[None]:
    try:
        yield
    except httpx.HTTPError as e:
        log.error(f"Failed to reach DIAL Core: {e}")
        raise DIALException("Failed to reach DIAL Core", status_code=502) from e
