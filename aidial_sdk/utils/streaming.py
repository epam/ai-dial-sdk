import json
from typing import Any, AsyncGenerator, Dict, Union

from aidial_sdk.chat_completion.chunks import BaseChunkWithDefaults
from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.utils.logging import log_debug
from aidial_sdk.utils.merge_chunks import cleanup_indices, merge

_DONE_MARKER = "[DONE]"


async def merge_chunks(
    chunk_stream: AsyncGenerator[dict, None]
) -> Dict[str, Any]:
    response: Dict[str, Any] = {}
    async for chunk in chunk_stream:
        response = merge(response, chunk)

    for choice in response["choices"]:
        choice["message"] = cleanup_indices(choice["delta"])
        del choice["delta"]

    return response


def _format_chunk(data: Union[dict, str]) -> str:
    data = "data: " + (
        json.dumps(data, separators=(",", ":"))
        if isinstance(data, dict)
        else data
    )
    log_debug(data)
    return f"{data}\n\n"


ResponseStream = AsyncGenerator[
    Union[BaseChunkWithDefaults, DIALException], None
]


async def _handle_exceptions_in_block_response(
    stream: ResponseStream,
) -> AsyncGenerator[dict, None]:
    is_first_chunk = True

    async for chunk in stream:
        if isinstance(chunk, DIALException):
            raise chunk.to_fastapi_exception()
        else:
            # Setting defaults only for the first chunk to make
            # the follow-up merging logic simpler.
            yield chunk.to_dict(with_defaults=is_first_chunk)

        is_first_chunk = False


async def to_block_response(stream: ResponseStream) -> dict:
    chunk_stream = _handle_exceptions_in_block_response(stream)
    return await merge_chunks(chunk_stream)


async def to_streaming_response(
    stream: ResponseStream,
) -> AsyncGenerator[str, None]:

    first_chunk = await stream.__anext__()

    if isinstance(first_chunk, DIALException):
        raise first_chunk.to_fastapi_exception()

    async def _generator() -> AsyncGenerator[str, None]:
        yield _format_chunk(first_chunk.to_dict(with_defaults=True))

        async for chunk in stream:
            if isinstance(chunk, DIALException):
                yield _format_chunk(chunk.json_error())
            else:
                yield _format_chunk(chunk.to_dict(with_defaults=True))

        yield _format_chunk(_DONE_MARKER)

    return _generator()
