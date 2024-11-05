from types import TracebackType
from typing import Optional, Type, overload

from aidial_sdk.chat_completion._types import ChunkQueue
from aidial_sdk.chat_completion.chunks import (
    AttachmentStageChunk,
    ContentStageChunk,
    FinishStageChunk,
    NameStageChunk,
    StartStageChunk,
)
from aidial_sdk.chat_completion.enums import Status
from aidial_sdk.chat_completion.request import Attachment
from aidial_sdk.pydantic_v1 import ValidationError
from aidial_sdk.utils._attachment import create_attachment
from aidial_sdk.utils._content_stream import ContentStream
from aidial_sdk.utils.errors import runtime_error


class Stage:
    _queue: ChunkQueue
    _choice_index: int
    _stage_index: int
    _name: Optional[str]
    _last_attachment_index: int
    _closed: bool
    _opened: bool

    def __init__(
        self,
        queue: ChunkQueue,
        choice_index: int,
        stage_index: int,
        name: Optional[str] = None,
    ):
        self._queue = queue
        self._choice_index = choice_index
        self._stage_index = stage_index
        self._last_attachment_index = 0
        self._opened = False
        self._closed = False
        self._name = name

    def __enter__(self):
        self.open()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> Optional[bool]:
        if not exc:
            if not self._closed:
                self.close(Status.COMPLETED)
        else:
            self.close(Status.FAILED)

        return False

    def append_content(self, content: str):
        if not self._opened:
            raise runtime_error("Trying to append content to an unopened stage")
        if self._closed:
            raise runtime_error("Trying to append content to a closed stage")

        self._queue.put_nowait(
            ContentStageChunk(self._choice_index, self._stage_index, content)
        )

    @property
    def content_stream(self) -> ContentStream:
        return ContentStream(self)

    def append_name(self, name: str):
        if not self._opened:
            raise runtime_error("Trying to append name to an unopened stage")
        if self._closed:
            raise runtime_error("Trying to append name to a closed stage")

        self._queue.put_nowait(
            NameStageChunk(self._choice_index, self._stage_index, name)
        )

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
            raise runtime_error("Trying to add attachment to an unopened stage")
        if self._closed:
            raise runtime_error("Trying to add attachment to a closed stage")

        attachment_stage_chunk = None
        try:
            attachment_stage_chunk = AttachmentStageChunk(
                choice_index=self._choice_index,
                stage_index=self._stage_index,
                attachment_index=self._last_attachment_index,
                **create_attachment(*args, **kwargs).dict(),
            )
        except ValidationError as e:
            raise runtime_error(e.errors()[0]["msg"])

        self._queue.put_nowait(attachment_stage_chunk)
        self._last_attachment_index += 1

    def open(self):
        if self._opened:
            raise runtime_error("The stage is already open")

        self._opened = True
        self._queue.put_nowait(
            StartStageChunk(self._choice_index, self._stage_index, self._name)
        )

    def close(self, status: Status = Status.COMPLETED):
        if not self._opened:
            raise runtime_error("Trying to close an unopened stage")
        if self._closed:
            raise runtime_error("The stage is already closed")

        self._closed = True
        self._queue.put_nowait(
            FinishStageChunk(self._choice_index, self._stage_index, status)
        )
