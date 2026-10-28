import contextlib
import logging
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable
from functools import wraps

from fastapi import Request
from fastapi.responses import Response, StreamingResponse

from aidial_sdk.translators.messages_to_chat_completions.errors import (
    AnthropicErrorType,
    anthropic_error_response,
)
from aidial_sdk.translators.messages_to_chat_completions.utils.log_config import (
    bedrock_logger as log,
)


async def not_found(request: Request) -> Response:
    return anthropic_error_response(
        AnthropicErrorType.NOT_FOUND, f"Unknown endpoint: {request.url.path}"
    )


def _as_text(data: str | bytes | memoryview) -> str:
    if isinstance(data, str):
        return data
    return bytes(data).decode("utf-8", errors="replace")


async def _log_stream_chunks(
    iterator: AsyncIterable[str | bytes | memoryview],
) -> AsyncIterator[str | bytes | memoryview]:
    async for chunk in iterator:
        with contextlib.suppress(Exception):
            log.debug(f"response chunk: {_as_text(chunk).rstrip()}")
        yield chunk


def with_debug_logging(
    func: Callable[[Request], Awaitable[Response]],
) -> Callable[[Request], Awaitable[Response]]:
    def one_line(text: str) -> str:
        return "".join(text.splitlines())

    @wraps(func)
    async def wrapper(request: Request) -> Response:
        if not log.isEnabledFor(logging.DEBUG):
            return await func(request)

        with contextlib.suppress(Exception):
            log.debug(f"request: {one_line(_as_text(await request.body()))}")

        response = await func(request)

        if isinstance(response, StreamingResponse):
            response.body_iterator = _log_stream_chunks(response.body_iterator)
        else:
            with contextlib.suppress(Exception):
                log.debug(f"response: {one_line(_as_text(response.body))}")

        return response

    return wrapper
