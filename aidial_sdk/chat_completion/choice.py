import json
from asyncio import Queue
from types import TracebackType
from typing import Any, List, Optional, Type

from aidial_sdk.chat_completion.chunks import (
    AttachmentChunk,
    BaseChunk,
    ContentChunk,
    EndChoiceChunk,
    FunctionCallChunk,
    StartChoiceChunk,
    StateChunk,
    ToolCallsChunk,
)
from aidial_sdk.chat_completion.enums import FinishReason
from aidial_sdk.chat_completion.request import FunctionCall, ToolCall
from aidial_sdk.chat_completion.stage import Stage
from aidial_sdk.pydantic_v1 import ValidationError
from aidial_sdk.utils.errors import runtime_error
from aidial_sdk.utils.logging import log_debug


class Choice:
    _queue: Queue
    _index: int
    _last_attachment_index: int
    _last_stage_index: int
    _opened: bool
    _closed: bool
    _state_submitted: bool
    _finish_reason: Optional[FinishReason]

    def __init__(self, queue: Queue, choice_index: int):
        self._queue = queue
        self._index = choice_index
        self._last_attachment_index = 0
        self._last_stage_index = 0
        self._opened = False
        self._closed = False
        self._state_submitted = False
        self._finish_reason = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> Optional[bool]:
        self.close()
        return False

    def _enqueue(self, chunk: BaseChunk) -> None:
        log_debug("chunk: " + json.dumps(chunk.to_dict()))
        self._queue.put_nowait(chunk)

    def append_content(self, content: str) -> None:
        if not self._opened:
            raise runtime_error(
                "Trying to append content to an unopened choice"
            )
        if self._closed:
            raise runtime_error("Trying to append content to a closed choice")
        if (
            self._finish_reason is not None
            and self._finish_reason != FinishReason.STOP
        ):
            raise runtime_error(
                "Trying to append content to a choice "
                "which is not allowed to have content, "
                f"because it's marked with '{self._finish_reason}' finish reason"
            )

        self._enqueue(ContentChunk(content, self._index))
        self._finish_reason = FinishReason.STOP

    def add_tool_calls(self, tool_calls: List[ToolCall]) -> None:
        if not self._opened:
            raise runtime_error(
                "Trying to add tool calls to an unopened choice"
            )
        if self._closed:
            raise runtime_error("Trying to add tool calls to a closed choice")
        if self._finish_reason is not None:
            raise runtime_error(
                "Trying to add tool calls to a choice which "
                "is not allowed to have tool calls, "
                f"because it's marked with '{self._finish_reason}' finish reason"
            )

        self._enqueue(ToolCallsChunk(tool_calls, self._index))
        self._finish_reason = FinishReason.TOOL_CALLS

    def add_function_call(self, function_call: FunctionCall) -> None:
        if not self._opened:
            raise runtime_error(
                "Trying to add function call to an unopened choice"
            )
        if self._closed:
            raise runtime_error(
                "Trying to add function call to a closed choice"
            )
        if self._finish_reason is not None:
            raise runtime_error(
                "Trying to add function call to a choice which, "
                f"because it's marked with '{self._finish_reason}' finish reason"
            )

        self._enqueue(FunctionCallChunk(function_call, self._index))
        self._finish_reason = FinishReason.FUNCTION_CALL

    def add_attachment(
        self,
        type: Optional[str] = None,
        title: Optional[str] = None,
        data: Optional[str] = None,
        url: Optional[str] = None,
        reference_url: Optional[str] = None,
        reference_type: Optional[str] = None,
    ) -> None:
        if not self._opened:
            raise runtime_error(
                "Trying to add attachment to an unopened choice"
            )
        if self._closed:
            raise runtime_error("Trying to add attachment to a closed choice")

        attachment_chunk = None
        try:
            attachment_chunk = AttachmentChunk(
                choice_index=self._index,
                attachment_index=self._last_attachment_index,
                type=type,
                title=title,
                data=data,
                url=url,
                reference_url=reference_url,
                reference_type=reference_type,
            )
        except ValidationError as e:
            raise runtime_error(e.errors()[0]["msg"])

        self._enqueue(attachment_chunk)
        self._last_attachment_index += 1

    def set_state(self, state: Any) -> None:
        if self._state_submitted:
            raise runtime_error('Trying to set "state" twice')

        if not self._opened:
            raise runtime_error("Trying to append state to an unopened choice")
        if self._closed:
            raise runtime_error("Trying to append state to a closed choice")

        self._state_submitted = True
        self._enqueue(StateChunk(self._index, state))

    def create_stage(self, name: Optional[str] = None) -> Stage:
        if not self._opened:
            raise runtime_error("Trying to create stage to an unopened choice")
        if self._closed:
            raise runtime_error("Trying to create stage to a closed choice")

        stage = Stage(self._queue, self._index, self._last_stage_index, name)
        self._last_stage_index += 1

        return stage

    def open(self):
        if self._opened:
            raise runtime_error("The choice is already open")

        self._opened = True
        self._enqueue(StartChoiceChunk(choice_index=self._index))

    def close(self, finish_reason: Optional[FinishReason] = None) -> None:
        if not self._opened:
            raise runtime_error("Trying to close an unopened choice")
        if self._closed:
            raise runtime_error(
                "Trying to close a choice which is already closed"
            )

        if (
            self._finish_reason is not None
            and finish_reason is not None
            and finish_reason != self._finish_reason
        ):
            raise runtime_error(
                f"Trying to close a choice with a finish reason '{finish_reason}' "
                f"which doesn't match the previously set one '{self._finish_reason}'"
            )

        if self._finish_reason is None and finish_reason in [
            FinishReason.FUNCTION_CALL,
            FinishReason.TOOL_CALLS,
        ]:
            raise runtime_error(
                f"Can't close a choice with a finish reason '{finish_reason}' without "
                " setting corresponding content"
            )

        reason = self._finish_reason or finish_reason or FinishReason.STOP

        self._closed = True
        self._enqueue(EndChoiceChunk(reason, self._index))
