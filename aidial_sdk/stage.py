from asyncio import Queue
from typing import Optional

from aidial_sdk.chat_completion.chunks import (
    AttachmentStageChunk,
    ContentStageChunk,
    FinishStageChunk,
    StartStageChunk,
)


class Stage:
    queue: Queue
    choice_index: int
    stage_index: int
    name: str
    last_attachment_index: int
    finished: bool

    def __init__(
        self, queue: Queue, choice_index: int, stage_index: int, name: str
    ):
        self.queue = queue
        self.choice_index = choice_index
        self.stage_index = stage_index
        self.last_attachment_index = 0
        self.finished = False
        self.name = name

    def __enter__(self):
        self.start(self.name)
        return self

    def __exit__(self, type, value, traceback):
        self.finish("completed")

    def start(self, name: str):
        self.queue.put_nowait(
            StartStageChunk(self.choice_index, self.stage_index, name)
        )

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

    def finish(self, status: str):
        if self.finished:
            pass  # TODO: logging
            return

        self.queue.put_nowait(
            FinishStageChunk(self.choice_index, self.stage_index, status)
        )
        self.finished = True
