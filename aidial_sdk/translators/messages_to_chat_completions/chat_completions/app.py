import json
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx
from anthropic.types.beta.message_create_params import MessageCreateParams
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from aidial_sdk._constants import DIAL_SDK_SSE_HEARTBEAT_INTERVAL
from aidial_sdk._errors import error_handler
from aidial_sdk.deployment.from_request_mixin import get_client_deployment_id
from aidial_sdk.exceptions import InvalidRequestError, ResourceNotFoundError
from aidial_sdk.translators.messages_to_chat_completions.backend.client import (
    ChatClient,
)
from aidial_sdk.translators.messages_to_chat_completions.backend.http import (
    ChatClientHttp,
    core_headers,
    core_legacy_client,
    core_v1_client,
)
from aidial_sdk.translators.messages_to_chat_completions.chat_completions.from_chat_completions import (
    to_anthropic_response,
)
from aidial_sdk.translators.messages_to_chat_completions.chat_completions.streaming import (
    translate_stream,
)
from aidial_sdk.translators.messages_to_chat_completions.chat_completions.to_chat_completions import (
    to_chat_completions_request,
)
from aidial_sdk.translators.messages_to_chat_completions.settings import (
    get_dial_url,
)
from aidial_sdk.translators.messages_to_chat_completions.translation_state import (
    TranslationState,
)
from aidial_sdk.utils._logging_middleware import LoggingMiddleware
from aidial_sdk.utils.logging import logger as log

ClientT = TypeVar("ClientT")
ClientFactory = Callable[[Request], Awaitable[ClientT]] | ClientT


async def _not_found(request: Request) -> Response:
    error = ResourceNotFoundError(f"Unknown endpoint: {request.url.path}")
    return error.to_fastapi_response("anthropic")


async def handle_anthropic_messages(
    request: Request, client: ChatClient
) -> Response:
    deployment = get_client_deployment_id(request.headers)

    try:
        req: MessageCreateParams = await request.json()
    except ValueError as e:
        raise InvalidRequestError(f"Request body is not valid JSON: {e}") from e

    translation_state = TranslationState()
    chat_request = to_chat_completions_request(
        req, deployment, translation_state
    )

    body = chat_request.model_dump(mode="json", exclude_none=True)
    if log.isEnabledFor(logging.DEBUG):
        log.debug(f"chat request: {json.dumps(body)}")

    if chat_request.stream:
        events, headers = await client.create_stream(body)
        resp = StreamingResponse(
            translate_stream(events, deployment, translation_state),
            media_type="text/event-stream",
        )
    else:
        completion, headers = await client.create_block(body)
        message = to_anthropic_response(
            completion, deployment, translation_state
        )
        resp = JSONResponse(
            content=message.model_dump(mode="json", exclude_unset=True)
        )

    for key, value in headers:
        resp.headers.append(key, value)

    return resp


def create_anthropic_api_app(
    get_client: ClientFactory[httpx.AsyncClient],
) -> FastAPI:
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    async def _chat_client(request: Request, *, legacy: bool) -> ChatClientHttp:
        http_client = (
            await get_client(request) if callable(get_client) else get_client
        )
        dial_url = get_dial_url()
        if legacy:
            deployment_id = get_client_deployment_id(request.headers)
            client = core_legacy_client(dial_url, deployment_id, http_client)
        else:
            client = core_v1_client(dial_url, http_client)

        return ChatClientHttp(
            client, core_headers(request), DIAL_SDK_SSE_HEARTBEAT_INTERVAL
        )

    @app.post("/anthropic/v1/messages")
    @error_handler("anthropic")
    async def _handle_v1_messages(request: Request) -> Response:
        return await handle_anthropic_messages(
            request, await _chat_client(request, legacy=False)
        )

    @app.post("/legacy/anthropic/v1/messages")
    @error_handler("anthropic")
    async def _handle_legacy_messages(request: Request) -> Response:
        return await handle_anthropic_messages(
            request, await _chat_client(request, legacy=True)
        )

    app.add_api_route(
        "/{full_path:path}",
        _not_found,
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    )

    return app
