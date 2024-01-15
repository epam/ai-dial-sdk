from enum import Enum


class FinishReason(Enum):
    STOP = "stop"
    LENGTH = "length"
    FUNCTION_CALL = "function_call"
    TOOL_CALLS = "tool_calls"
    CONTENT_FILTER = "content_filter"


class Status(Enum):
    COMPLETED = "completed"
    FAILED = "failed"
