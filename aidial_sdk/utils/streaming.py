import json
from typing import Any, AsyncGenerator, Dict, Optional

from aidial_sdk.utils.merge_chunks import merge_recursive

DONE_CHUNK = "data: DONE\n"


def add_default_fields(
    target: Dict[str, Any],
    response_id: str,
    model: Optional[str],
    created: int,
    type: str,
) -> None:
    target["id"] = response_id
    if model:
        target["model"] = model
    target["created"] = created
    target["object"] = type


async def merge_chunks(
    chunk_stream: AsyncGenerator[Any, None]
) -> Dict[str, Any]:
    response: Any = None
    async for chunk in chunk_stream:
        if response == None:
            response = chunk
        else:
            response["choices"] = merge_recursive(
                response["choices"], chunk["choices"], []
            )

        statistics = chunk.get("statistics", None)
        if statistics:
            if response.get("statistics", None) == None:
                response["statistics"] = statistics
            else:
                response["statistics"] = merge_recursive(
                    response["statistics"], statistics, []
                )

        if chunk["usage"]:
            response["usage"] = chunk["usage"]

    for choice in response["choices"]:
        choice["message"] = choice["delta"]
        del choice["delta"]

    return response


def generate_chunk(data: Any):
    return "data: " + json.dumps(data, separators=(",", ":")) + "\n\n"
