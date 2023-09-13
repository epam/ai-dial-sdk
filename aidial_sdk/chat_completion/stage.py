from asyncio import Queue
from types import TracebackType
from typing import Optional, Type

from aidial_sdk.chat_completion.chunks import (
    AttachmentStageChunk,
    ContentStageChunk,
    FinishStageChunk,
    StartStageChunk,
)
from aidial_sdk.chat_completion.enums import Status


class Stage:
    queue: Queue
    choice_index: int
    stage_index: int
    name: str
    last_attachment_index: int
    closed: bool

    def __init__(
        self, queue: Queue, choice_index: int, stage_index: int, name: str
    ):
        self.queue = queue
        self.choice_index = choice_index
        self.stage_index = stage_index
        self.last_attachment_index = 0
        self.closed = False
        self.name = name

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
            self.close()

        return False

    def content(self, content: str):
        self.queue.put_nowait(
            ContentStageChunk(self.choice_index, self.stage_index, content)
        )

    def attachment(
        self,
        type: Optional[str] = None,
        title: Optional[str] = None,
        data: Optional[str] = None,
        url: Optional[str] = None,
        reference_url: Optional[str] = None,
        reference_type: Optional[str] = None,
    ) -> None:
        self.queue.put_nowait(
            AttachmentStageChunk(
                self.choice_index,
                self.stage_index,
                self.last_attachment_index,
                type,
                title,
                data,
                url,
                reference_url,
                reference_type,
            )
        )
        self.last_attachment_index += 1

    def open(self):
        self.queue.put_nowait(
            StartStageChunk(self.choice_index, self.stage_index, self.name)
        )

    def close(self, status: Status = Status.COMPLETED):
        if self.closed:
            pass  # TODO: exception
            return

        self.queue.put_nowait(
            FinishStageChunk(self.choice_index, self.stage_index, status)
        )
        self.closed = True
