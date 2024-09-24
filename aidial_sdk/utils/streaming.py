import json
from typing import Any, AsyncIterator

from aidial_sdk.utils.logging import log_debug

DONE_MARKER = "[DONE]"


def format_chunk(data: Any):
    data = "data: " + (
        json.dumps(data, separators=(",", ":"))
        if isinstance(data, dict)
        else data
    )
    log_debug(data)
    return f"{data}\n\n"


async def to_sse_stream(stream: AsyncIterator[dict]) -> AsyncIterator[str]:
    async for chunk in stream:
        yield format_chunk(chunk)
    yield format_chunk(DONE_MARKER)
