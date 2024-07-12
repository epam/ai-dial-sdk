from enum import Enum


class FinishReason(str, Enum):
    STOP = "stop"
    LENGTH = "length"
    FUNCTION_CALL = "function_call"
    TOOL_CALLS = "tool_calls"
    CONTENT_FILTER = "content_filter"


class Status(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
