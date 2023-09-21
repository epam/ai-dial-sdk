from enum import Enum


class FinishReason(Enum):
    STOP = "stop"
    LENGTH = "length"
    FUNCTION_CALL = "function_call"
    CONTENT_FILTER = "content_filter"


class Status(Enum):
    COMPLETED = "completed"
    FAILED = "failed"
