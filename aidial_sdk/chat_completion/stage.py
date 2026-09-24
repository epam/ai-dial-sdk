from types import TracebackType
from typing import TYPE_CHECKING, overload

from aidial_sdk._pydantic import ValidationError
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
from aidial_sdk.utils._attachment import create_attachment
from aidial_sdk.utils._content_stream import ContentStream
from aidial_sdk.utils.errors import runtime_error
from aidial_sdk.utils.logging import log_warning

if TYPE_CHECKING:
    from aidial_sdk.chat_completion.choice import Choice


class Stage:
    _choice: "Choice"
    _queue: ChunkQueue
    _choice_index: int
    _stage_index: int
    _name: str | None
    _parent: "Stage | None"
    _children: list["Stage"]
    _last_attachment_index: int
    _closed: bool
    _opened: bool

    def __init__(
        self,
        choice: "Choice",
        stage_index: int,
        name: str | None = None,
        parent: "Stage | None" = None,
    ):
        if parent is not None and parent._choice is not choice:
            raise runtime_error(
                "Trying to create a stage whose parent stage belongs to another choice"
            )

        self._choice = choice
        self._queue = choice._queue
        self._choice_index = choice.index
        self._stage_index = stage_index
        self._last_attachment_index = 0
        self._opened = False
        self._closed = False
        self._name = name
        self._parent = parent
        self._children = []

        if parent is not None:
            parent._children.append(self)

    @property
    def stage_index(self) -> int:
        return self._stage_index

    def create_stage(self, name: str | None = None) -> "Stage":
        return self._choice._create_stage(name, parent=self)

    def __enter__(self):
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        if not self._closed:
            status = Status.FAILED if exc else Status.COMPLETED
            self.close(status)

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
        type: str | None = None,
        title: str | None = None,
        data: str | None = None,
        url: str | None = None,
        reference_url: str | None = None,
        reference_type: str | None = None,
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
                **create_attachment(*args, **kwargs).model_dump(),
            )
        except ValidationError as e:
            raise runtime_error(e.errors()[0]["msg"])

        self._queue.put_nowait(attachment_stage_chunk)
        self._last_attachment_index += 1

    def open(self):
        if self._opened:
            raise runtime_error("The stage is already open")

        parent = self._parent
        if parent is not None:
            if not parent._opened:
                raise runtime_error(
                    "Trying to open a stage whose parent stage is not open"
                )
            if parent._closed:
                raise runtime_error(
                    "Trying to open a stage whose parent stage is already closed"
                )

        self._opened = True
        self._queue.put_nowait(
            StartStageChunk(
                self._choice_index,
                self._stage_index,
                self._name,
                parent._stage_index if parent is not None else None,
            )
        )

    def close(self, status: Status = Status.COMPLETED):
        if not self._opened:
            raise runtime_error("Trying to close an unopened stage")
        if self._closed:
            raise runtime_error("The stage is already closed")

        open_children = [
            child._stage_index
            for child in self._children
            if child._opened and not child._closed
        ]
        if open_children:
            log_warning(
                f"Closing the stage {self._stage_index} which still has "
                f"open child stages: {open_children}"
            )

        self._closed = True
        self._queue.put_nowait(
            FinishStageChunk(self._choice_index, self._stage_index, status)
        )
