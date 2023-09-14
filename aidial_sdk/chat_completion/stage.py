from asyncio import Queue
from logging import Logger
from types import TracebackType
from typing import Optional, Type

from aidial_sdk.chat_completion.chunks import (
    AttachmentStageChunk,
    ContentStageChunk,
    FinishStageChunk,
    StartStageChunk,
)
from aidial_sdk.chat_completion.enums import Status
from aidial_sdk.utils.errors import runtime_error


class Stage:
    _queue: Queue
    _choice_index: int
    _stage_index: int
    _name: str
    _last_attachment_index: int
    _closed: bool
    _opened: bool

    def __init__(
        self,
        queue: Queue,
        choice_index: int,
        stage_index: int,
        name: str,
        log: Logger,
    ):
        self._queue = queue
        self._choice_index = choice_index
        self._stage_index = stage_index
        self._last_attachment_index = 0
        self._opened = False
        self._closed = False
        self._name = name
        self._log = log

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
            self.close(Status.COMPLETED)
        else:
            self.close(Status.FAILED)

        return False

    def append_content(self, content: str):
        if not self._opened:
            runtime_error(
                self._log, "Trying to append content for an unopened stage"
            )
        if self._closed:
            runtime_error(
                self._log, "Trying to append content for a closed stage"
            )

        self._queue.put_nowait(
            ContentStageChunk(self._choice_index, self._stage_index, content)
        )

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
            runtime_error(
                self._log, "Trying to add attachment for an unopened stage"
            )
        if self._closed:
            runtime_error(
                self._log, "Trying to add attachment for a closed stage"
            )

        self._queue.put_nowait(
            AttachmentStageChunk(
                self._choice_index,
                self._stage_index,
                self._last_attachment_index,
                type,
                title,
                data,
                url,
                reference_url,
                reference_type,
            )
        )
        self._last_attachment_index += 1

    def open(self):
        if self._opened:
            runtime_error(self._log, "The stage is already open")

        self._opened = True
        self._queue.put_nowait(
            StartStageChunk(self._choice_index, self._stage_index, self._name)
        )

    def close(self, status: Status = Status.COMPLETED):
        if not self._opened:
            runtime_error(self._log, "Trying to close an unopened stage")
        if self._closed:
            runtime_error(self._log, "The stage is already closed")

        self._closed = True
        self._queue.put_nowait(
            FinishStageChunk(self._choice_index, self._stage_index, status)
        )
