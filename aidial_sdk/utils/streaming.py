from typing import Any, AsyncGenerator, Dict

from aidial_sdk.utils.merge_chunks import merge

DONE_CHUNK = "data: [DONE]\n\n"


async def merge_chunks(
    chunk_stream: AsyncGenerator[Any, None]
) -> Dict[str, Any]:
    response: Dict[str, Any] = {}
    async for chunk in chunk_stream:
        response = merge(response, chunk)

    for choice in response["choices"]:
        choice["message"] = choice["delta"]
        del choice["delta"]

    return response
