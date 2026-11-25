from uuid import uuid4

RESPONSE_PREFIX = "resp"
MESSAGE_PREFIX = "msg"
REASONING_PREFIX = "rs"
FUNCTION_CALL_PREFIX = "fc"
CUSTOM_TOOL_CALL_PREFIX = "ctc"
WEB_SEARCH_PREFIX = "ws"
IMAGE_GENERATION_PREFIX = "ig"
CALL_PREFIX = "call"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"
