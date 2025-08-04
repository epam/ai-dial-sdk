import json
from types import TracebackType
from typing import Any, Optional, Type, overload

from aidial_sdk._pydantic import ValidationError
from aidial_sdk.chat_completion._types import ChunkQueue
from aidial_sdk.chat_completion.choice_base import ChoiceBase
from aidial_sdk.chat_completion.chunks import (
    AttachmentChunk,
    BaseChunk,
    ContentChunk,
    EndChoiceChunk,
    FormSchemaChunk,
    StartChoiceChunk,
    StateChunk,
)
from aidial_sdk.chat_completion.enums import FinishReason
from aidial_sdk.chat_completion.function_call import FunctionCall
from aidial_sdk.chat_completion.function_tool_call import FunctionToolCall
from aidial_sdk.chat_completion.request import Attachment
from aidial_sdk.chat_completion.stage import Stage
from aidial_sdk.utils._attachment import create_attachment
from aidial_sdk.utils._content_stream import ContentStream
from aidial_sdk.utils.errors import runtime_error
from aidial_sdk.utils.logging import log_debug


class Choice(ChoiceBase):
    _queue: ChunkQueue
    _index: int
    _last_attachment_index: int
    _last_stage_index: int
    _last_tool_call_index: int
    _has_function_call: bool
    _opened: bool
    _closed: bool
    _state_submitted: bool
    _schema_submitted: bool
    _last_finish_reason: Optional[FinishReason]

    def __init__(self, queue: ChunkQueue, choice_index: int):
        self._queue = queue
        self._index = choice_index
        self._last_attachment_index = 0
        self._last_stage_index = 0
        self._last_tool_call_index = 0
        self._has_function_call = False
        self._opened = False
        self._closed = False
        self._state_submitted = False
        self._schema_submitted = False
        self._last_finish_reason = None

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

    def send_chunk(self, chunk: BaseChunk) -> None:
        log_debug("chunk: " + json.dumps(chunk.to_dict()))
        self._queue.put_nowait(chunk)

    @property
    def index(self) -> int:
        return self._index

    @property
    def opened(self) -> bool:
        return self._opened

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def has_function_call(self) -> bool:
        return self._has_function_call

    def append_content(self, content: str) -> None:
        if not self._opened:
            raise runtime_error(
                "Trying to append content to an unopened choice"
            )
        if self._closed:
            raise runtime_error("Trying to append content to a closed choice")

        self.send_chunk(ContentChunk(content, self._index))
        self._last_finish_reason = FinishReason.STOP

    @property
    def content_stream(self) -> ContentStream:
        return ContentStream(self)

    def create_function_tool_call(
        self, id: str, name: str, arguments: Optional[str] = None
    ) -> FunctionToolCall:
        function_tool_call = FunctionToolCall.create_and_send(
            self, self._last_tool_call_index, id, name, arguments
        )
        self._last_tool_call_index += 1
        self._last_finish_reason = FinishReason.TOOL_CALLS
        return function_tool_call

    def create_function_call(
        self, name: str, arguments: Optional[str] = None
    ) -> FunctionCall:
        function_call = FunctionCall.create_and_send(self, name, arguments)
        self._has_function_call = True
        self._last_finish_reason = FinishReason.FUNCTION_CALL
        return function_call

    @overload
    def add_attachment(self, attachment: Attachment) -> None: ...

    @overload
    def add_attachment(
        self,
        type: Optional[str] = None,
        title: Optional[str] = None,
        data: Optional[str] = None,
        url: Optional[str] = None,
        reference_url: Optional[str] = None,
        reference_type: Optional[str] = None,
    ) -> None: ...

    def add_attachment(self, *args, **kwargs) -> None:
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
                **create_attachment(*args, **kwargs).model_dump(),
            )
        except ValidationError as e:
            raise runtime_error(e.errors()[0]["msg"])

        self.send_chunk(attachment_chunk)
        self._last_attachment_index += 1

    def set_state(self, state: Any) -> None:
        if self._state_submitted:
            raise runtime_error('Trying to set "state" twice')

        if not self._opened:
            raise runtime_error("Trying to append state to an unopened choice")
        if self._closed:
            raise runtime_error("Trying to append state to a closed choice")

        self._state_submitted = True
        self.send_chunk(StateChunk(self._index, state))

    def set_form_schema(self, form_schema: Any) -> None:
        if self._schema_submitted:
            raise runtime_error("Trying to set form schema twice")

        if not self._opened:
            raise runtime_error(
                "Trying to append form schema to an unopened choice"
            )
        if self._closed:
            raise runtime_error(
                "Trying to append form schema to a closed choice"
            )

        self._schema_submitted = True
        self.send_chunk(FormSchemaChunk(self._index, form_schema))

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
        self.send_chunk(StartChoiceChunk(choice_index=self._index))

    def close(self, finish_reason: Optional[FinishReason] = None) -> None:
        if not self._opened:
            raise runtime_error("Trying to close an unopened choice")
        if self._closed:
            raise runtime_error(
                "Trying to close a choice which is already closed"
            )

        reason = finish_reason or self._last_finish_reason or FinishReason.STOP

        self._closed = True
        self.send_chunk(EndChoiceChunk(reason, self._index))
