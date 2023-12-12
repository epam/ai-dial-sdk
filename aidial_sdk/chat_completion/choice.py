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

    def __init__(self, queue: Queue, choice_index: int):
        self._queue = queue
        self._index = choice_index
        self._last_attachment_index = 0
        self._last_stage_index = 0
        self._opened = False
        self._closed = False
        self._state_submitted = False

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
        log_debug("added chunk:\n", chunk.to_dict())
        self._queue.put_nowait(chunk)

    def append_content(self, content: str) -> None:
        if not self._opened:
            runtime_error("Trying to append content to an unopened choice")
        if self._closed:
            runtime_error("Trying to append content to a closed choice")

        self._enqueue(ContentChunk(content, self._index))

    def add_tool_calls(self, tool_calls: List[ToolCall]) -> None:
        if not self._opened:
            runtime_error("Trying to add tool call to an unopened choice")
        if self._closed:
            runtime_error("Trying to add tool call to a closed choice")

        self._enqueue(ToolCallsChunk(tool_calls, self._index))

    def add_function_call(self, function_call: FunctionCall) -> None:
        if not self._opened:
            runtime_error("Trying to add function call to an unopened choice")
        if self._closed:
            runtime_error("Trying to add function call to a closed choice")

        self._enqueue(FunctionCallChunk(function_call, self._index))

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
            runtime_error("Trying to add attachment to an unopened choice")
        if self._closed:
            runtime_error("Trying to add attachment to a closed choice")

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
            runtime_error(e.errors()[0]["msg"])

        # FIXME: remove the assert
        assert attachment_chunk is not None
        self._enqueue(attachment_chunk)
        self._last_attachment_index += 1

    def set_state(self, state: Any) -> None:
        if self._state_submitted:
            runtime_error('Trying to set "state" twice')

        if not self._opened:
            runtime_error("Trying to append state to an unopened choice")
        if self._closed:
            runtime_error("Trying to append state to a closed choice")

        self._state_submitted = True
        self._enqueue(StateChunk(self._index, state))

    def create_stage(self, name: Optional[str] = None) -> Stage:
        if not self._opened:
            runtime_error("Trying to create stage to an unopened choice")
        if self._closed:
            runtime_error("Trying to create stage to a closed choice")

        stage = Stage(self._queue, self._index, self._last_stage_index, name)
        self._last_stage_index += 1

        return stage

    def open(self):
        if self._opened:
            runtime_error("The choice is already open")

        self._opened = True
        self._enqueue(StartChoiceChunk(choice_index=self._index))

    def close(self, finish_reason: FinishReason = FinishReason.STOP) -> None:
        if not self._opened:
            runtime_error("Trying to close an unopened choice")
        if self._closed:
            runtime_error("The choice is already closed")

        self._closed = True
        self._enqueue(EndChoiceChunk(finish_reason, self._index))
