import json
import logging

from anthropic.types.beta.message_create_params import MessageCreateParams
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from openai import AsyncStream
from openai.types.chat import ChatCompletion, ChatCompletionChunk

from aidial_sdk.translators.messages_to_chat_completions.chat_completions.from_chat_completions import (
    to_anthropic_response,
)
from aidial_sdk.translators.messages_to_chat_completions.chat_completions.streaming import (
    translate_stream,
)
from aidial_sdk.translators.messages_to_chat_completions.chat_completions.to_chat_completions import (
    to_chat_completions_request,
)
from aidial_sdk.translators.messages_to_chat_completions.common import (
    not_found,
    with_debug_logging,
)
from aidial_sdk.translators.messages_to_chat_completions.core_client import (
    core_headers,
    core_legacy_client,
    core_v1_client,
)
from aidial_sdk.translators.messages_to_chat_completions.errors import (
    AnthropicErrorType,
    AnthropicHTTPError,
    translator_error_handler,
)
from aidial_sdk.translators.messages_to_chat_completions.settings import (
    get_dial_url,
)
from aidial_sdk.translators.messages_to_chat_completions.translation_state import (
    TranslationState,
)
from aidial_sdk.translators.messages_to_chat_completions.utils.log_config import (
    bedrock_logger as log,
)

app = FastAPI()


async def _handle_messages(request: Request, legacy: bool) -> Response:
    dial_url = get_dial_url()
    translation_state = TranslationState()

    try:
        req: MessageCreateParams = await request.json()
    except ValueError as e:
        raise AnthropicHTTPError(
            AnthropicErrorType.INVALID_REQUEST,
            f"Request body is not valid JSON: {e}",
        ) from e

    deployment = request.headers.get("x-dial-deployment-id") or req["model"]
    chat_request = to_chat_completions_request(
        req, deployment, translation_state
    )

    body = chat_request.model_dump(mode="json", exclude_none=True)
    if log.isEnabledFor(logging.DEBUG):
        log.debug(f"Translated request to Core: {json.dumps(body)}")

    client = (
        core_legacy_client(dial_url, deployment)
        if legacy
        else core_v1_client(dial_url)
    )
    headers = core_headers(request)

    if chat_request.stream:
        events = await client.post(
            "/chat/completions",
            cast_to=ChatCompletion,
            body=body,
            options={"headers": headers},
            stream=True,
            stream_cls=AsyncStream[ChatCompletionChunk],
        )
        return StreamingResponse(
            translate_stream(events, deployment, translation_state),
            media_type="text/event-stream",
        )

    response = await client.post(
        "/chat/completions",
        cast_to=ChatCompletion,
        body=body,
        options={"headers": headers},
    )
    message = to_anthropic_response(response, deployment, translation_state)
    return JSONResponse(
        content=message.model_dump(mode="json", exclude_unset=True)
    )


@app.post("/anthropic/v1/messages")
@with_debug_logging
@translator_error_handler
async def _handle_v1_messages(request: Request) -> Response:
    return await _handle_messages(request, legacy=False)


@app.post("/legacy/anthropic/v1/messages")
@with_debug_logging
@translator_error_handler
async def _handle_legacy_messages(request: Request) -> Response:
    return await _handle_messages(request, legacy=True)


app.add_api_route(
    "/{full_path:path}",
    not_found,
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
)
