import asyncio
import json
from typing import (
    Any,
    AsyncGenerator,
    Awaitable,
    Callable,
    Dict,
    Optional,
    TypeVar,
    Union,
    cast,
)

from typing_extensions import assert_never

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

ResponseStreamWithStr = AsyncGenerator[
    Union[BaseChunkWithDefaults, DIALException, str], None
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
    stream: ResponseStreamWithStr,
) -> AsyncGenerator[str, None]:

    first_chunk = await stream.__anext__()

    if isinstance(first_chunk, DIALException):
        raise first_chunk.to_fastapi_exception()

    def _chunk_to_str(
        chunk: Union[BaseChunkWithDefaults, DIALException, str]
    ) -> str:
        if isinstance(chunk, DIALException):
            return _format_chunk(chunk.json_error())
        elif isinstance(chunk, str):
            return chunk
        elif isinstance(chunk, BaseChunkWithDefaults):
            return _format_chunk(chunk.to_dict(with_defaults=True))
        else:
            assert_never(chunk)

    async def _generator() -> AsyncGenerator[str, None]:
        yield _chunk_to_str(first_chunk)

        async for chunk in stream:
            yield _chunk_to_str(chunk)

        yield _format_chunk(_DONE_MARKER)

    return _generator()


_T = TypeVar("_T")

_HeartbeatObject = Union[_T, Callable[[], Union[_T, Awaitable[_T]]]]
_HeartbeatCallback = Callable[[], Union[None, Awaitable[None]]]


async def _eval_heartbeat_object(o: _HeartbeatObject[_T]) -> _T:
    if callable(o):
        result = o()
        if isinstance(result, Awaitable):
            return await result
        return cast(_T, result)
    return o


async def _call_heartbeat_callback(c: _HeartbeatCallback) -> None:
    result = c()
    if isinstance(result, Awaitable):
        await result


async def add_heartbeat(
    stream: AsyncGenerator[_T, None],
    *,
    heartbeat_interval: float,
    heartbeat_object: Optional[_HeartbeatObject] = None,
    heartbeat_callback: Optional[_HeartbeatCallback] = None,
) -> AsyncGenerator[_T, None]:
    chunk_task: Optional[asyncio.Task[_T]] = None

    while True:
        if chunk_task is None:
            chunk_task = asyncio.create_task(stream.__anext__())

        done = (
            await asyncio.wait(
                [chunk_task],
                timeout=heartbeat_interval,
                return_when=asyncio.FIRST_COMPLETED,
            )
        )[0]

        if chunk_task in done:
            try:
                chunk, chunk_task = chunk_task.result(), None
                yield chunk
            except StopAsyncIteration:
                break
            except Exception as e:
                raise e
        else:
            if heartbeat_object is not None:
                yield await _eval_heartbeat_object(heartbeat_object)

            if heartbeat_callback is not None:
                await _call_heartbeat_callback(heartbeat_callback)
