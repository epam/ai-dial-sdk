import json
from typing import Any

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
