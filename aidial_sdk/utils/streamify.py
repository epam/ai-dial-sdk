"""
The module does the inverse of merging chunks:
it turn block response into a valid streaming chunk.
"""

import copy
from typing import Any


def _add_indices(chunk: Any) -> Any:
    if isinstance(chunk, list):
        ret = []
        for idx, elem in enumerate(chunk, start=1):
            if isinstance(elem, dict) and "index" not in elem:
                elem = {**elem, "index": idx}
            ret.append(_add_indices(elem))
        return ret

    if isinstance(chunk, dict):
        return {key: _add_indices(value) for key, value in chunk.items()}

    return chunk


def block_response_to_streaming_chunk(response: dict) -> dict:
    ret = copy.deepcopy(response)
    for choice in ret["choices"]:
        choice["delta"] = choice["message"]
        del choice["message"]
        choice["delta"] = _add_indices(choice["delta"])

    ret["object"] = "chat.completion.chunk"
    return ret
