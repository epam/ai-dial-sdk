import json
from typing import Any, AsyncGenerator, Dict

from aidial_sdk.chat_completion.chunk_accumulator import ChunkAccumulator
from aidial_sdk.utils.logging import log_debug

DONE_MARKER = "[DONE]"


async def merge_chunks(
    chunk_stream: AsyncGenerator[Any, None]
) -> Dict[str, Any]:
    acc = ChunkAccumulator()
    async for chunk in chunk_stream:
        acc.add_chunk(chunk)
    return acc.to_block_response()


def format_chunk(data: Any):
    data = "data: " + (
        json.dumps(data, separators=(",", ":"))
        if isinstance(data, dict)
        else data
    )
    log_debug(data)
    return f"{data}\n\n"
