import inspect
import json
import logging
from collections.abc import AsyncGenerator
from contextlib import aclosing
from http import HTTPStatus

from anthropic.types.beta.message_create_params import MessageCreateParams
from fastapi import Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from openai.types.responses import Response as ResponsesResponse
from pydantic import BaseModel, ValidationError
from starlette.datastructures import MutableHeaders

from aidial_sdk._errors import Handler
from aidial_sdk.deployment.from_request_mixin import get_client_deployment_id
from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.exceptions import InvalidRequestError
from aidial_sdk.translators._messages.sse_stream import (
    HEARTBEAT,
    Heartbeat,
)
from aidial_sdk.translators._messages.translation_state import (
    TranslationState,
)
from aidial_sdk.translators.messages_to_responses.from_responses import (
    to_anthropic_message,
)
from aidial_sdk.translators.messages_to_responses.streaming import (
    ResponsesEvent,
    translate_stream,
)
from aidial_sdk.translators.messages_to_responses.to_responses import (
    to_responses_request,
)
from aidial_sdk.utils._request import with_json_body
from aidial_sdk.utils.logging import logger as log


def to_messages_handler(responses_handler: Handler) -> Handler:
    """An Anthropic Messages API handler that translates the request for the
    Responses API handler and translates its response back."""

    async def _handler(request: Request) -> Response:
        try:
            req: MessageCreateParams = await request.json()
        except ValueError as e:
            raise InvalidRequestError(
                f"Request body is not valid JSON: {e}"
            ) from e

        translation_state = TranslationState()
        body = to_responses_request(req, translation_state)
        if log.isEnabledFor(logging.DEBUG):
            log.debug(f"responses request: {json.dumps(body)}")

        model = get_client_deployment_id(request.headers, req.get("model"))
        response = await _call(responses_handler, with_json_body(request, body))
        if response.status_code >= 400:
            raise await _to_dial_exception(response)

        headers = _without_body_headers(response)
        if body["stream"]:
            return StreamingResponse(
                translate_stream(
                    _read_events(response), model, translation_state
                ),
                media_type="text/event-stream",
                headers=headers,
                background=response.background,
            )

        message = to_anthropic_message(
            ResponsesResponse.model_construct(
                **json.loads(await _read_body(response))
            ),
            model,
            translation_state,
        )
        return JSONResponse(
            content=message.model_dump(mode="json", exclude_unset=True),
            headers=headers,
            background=response.background,
        )

    return _handler


async def _call(handler: Handler, request: Request) -> Response:
    try:
        return await handler(request)
    except Exception as e:
        # Answered the way the app answers it on the handler's own route,
        # where the handler of `Exception` serves only the unhandled ones,
        # which the error handler of this route logs and answers itself
        handlers = request.app.exception_handlers
        exception_handler = next(
            (
                handlers[cls]
                for cls in type(e).__mro__
                if cls in handlers and cls is not Exception
            ),
            None,
        )
        if exception_handler is None:
            raise
        response = exception_handler(request, e)
        return await response if inspect.isawaitable(response) else response


def _without_body_headers(response: Response) -> MutableHeaders:
    headers = response.headers
    # They describe the body of the handler, not the translated one
    for name in ("content-length", "content-encoding", "content-type"):
        del headers[name]
    return headers


class _Error(BaseModel):
    message: str


class _ErrorBody(BaseModel):
    error: _Error


async def _to_dial_exception(response: Response) -> DIALException:
    body = await _read_body(response)
    if response.background is not None:
        await response.background()
    try:
        message = _ErrorBody.model_validate_json(body).error.message
    except ValidationError:
        message = (
            body.decode(errors="replace")
            or HTTPStatus(response.status_code).phrase
        )
    return DIALException(
        message,
        status_code=response.status_code,
        headers=dict(_without_body_headers(response)),
    )


async def _read_body(response: Response) -> bytes:
    return b"".join([chunk async for chunk in _body_chunks(response)])


async def _body_chunks(response: Response) -> AsyncGenerator[bytes, None]:
    if not isinstance(response, StreamingResponse):
        yield bytes(response.body)
        return

    iterator = response.body_iterator
    try:
        async for chunk in iterator:
            yield (
                chunk.encode(response.charset)
                if isinstance(chunk, str)
                else bytes(chunk)
            )
    finally:
        # Releases what the handler holds, e.g. its upstream connection, when
        # the translation stops before the end of the body
        if isinstance(iterator, AsyncGenerator):
            await iterator.aclose()


async def _read_events(
    response: Response,
) -> AsyncGenerator[ResponsesEvent | Heartbeat, None]:
    """Parses the server-sent events of the body:
    https://html.spec.whatwg.org/multipage/server-sent-events.html"""

    data: list[str] = []
    async with aclosing(_read_lines(response)) as lines:
        async for line in lines:
            if line.startswith(":"):
                # A comment, which is how a server sends a heartbeat
                yield HEARTBEAT
            elif line.startswith("data:"):
                data.append(line.removeprefix("data:").removeprefix(" "))
            elif not line and data:
                if (event := "\n".join(data)) != "[DONE]":
                    yield json.loads(event)
                data = []


async def _read_lines(response: Response) -> AsyncGenerator[str, None]:
    buffer = b""
    async with aclosing(_body_chunks(response)) as chunks:
        async for chunk in chunks:
            *lines, buffer = (buffer + chunk).split(b"\n")
            for line in lines:
                yield line.removesuffix(b"\r").decode()
