from asyncio import Queue
from contextlib import contextmanager
from typing import Any, Iterator, Optional

from aidial_sdk.chat_completion.chunks import (
    AttachmentChunk,
    ContentChunk,
    EndChoiceChunk,
    StateChunk,
)
from aidial_sdk.stage import Stage


class Choice:
    queue: Queue
    index: int
    last_attachment_index: int
    last_stage_index: int
    finished: bool
    state_submitted: bool

    def __init__(self, queue: Queue, choice_index: int):
        self.queue = queue
        self.index = choice_index
        self.last_attachment_index = 0
        self.last_stage_index = 0
        self.finished = False
        self.state_submitted = False

    def content(self, content: str) -> None:
        self.queue.put_nowait(ContentChunk(content, self.index))

    def finish(self, finish_reason: str) -> None:
        if self.finished:
            # TODO: Generate warn to log
            return

        self.finished = True
        self.queue.put_nowait(EndChoiceChunk(finish_reason, self.index))

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
            AttachmentChunk(
                self.index,
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

    def state(self, state: Any) -> None:
        if self.state_submitted:
            # TODO: Generate warn to log
            return

        self.queue.put_nowait(StateChunk(self.index, state))
        self.state_submitted = True

    @contextmanager
    def stage(self, name: str) -> Iterator[Stage]:
        stage = Stage(self.queue, self.index, self.last_stage_index)
        stage.start(name)

        self.last_stage_index += 1

        try:
            yield stage
        finally:
            stage.finish("completed")
