import json
from typing import Any, AsyncGenerator, Dict

from aidial_sdk.utils.logging import log_debug
from aidial_sdk.utils.merge_chunks import cleanup_indices, merge

DONE_MARKER = "[DONE]"


async def merge_chunks(
    chunk_stream: AsyncGenerator[Any, None]
) -> Dict[str, Any]:
    response: Dict[str, Any] = {}
    async for chunk in chunk_stream:
        response = merge(response, chunk)

    for choice in response["choices"]:
        choice["message"] = cleanup_indices(choice["delta"])
        del choice["delta"]

    return response


def format_chunk(data: Any):
    data = "data: " + (
        json.dumps(data, separators=(",", ":"))
        if isinstance(data, dict)
        else data
    )
    log_debug(data)
    return f"{data}\n\n"
