from dialsdk.chat_completion.chunks import (
    DIALChatCompletionContentChunk,
    DIALChatCompletionEndChoiceChunk,
    DIALChatCompletionAttachmentChunk,
    DIALChatCompletionStateChunk,
)
from contextlib import contextmanager
from dialsdk.stage import Stage
from asyncio import Queue
from typing import Generator
from typing import Optional, Any
import asyncio


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
        self.queue.put_nowait(DIALChatCompletionContentChunk(content, self.index))

    # async def acontent(self, content: str) -> None:
    #     await self.queue.put(DIALChatCompletionContentChunk(content, self.index))

    def finish(self, finish_reason: str) -> None:
        if finished:
            # TODO: Generate warn to log
            return

        finished = True
        self.queue.put_nowait(
            DIALChatCompletionEndChoiceChunk(finish_reason, self.index)
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
            DIALChatCompletionAttachmentChunk(
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

        self.queue.put_nowait(DIALChatCompletionStateChunk(self.index, state))
        self.state_submitted = True

    @contextmanager
    def stage(self, name: str) -> Generator[Stage, None, None]:
        stage = Stage(self.queue, self.index, self.last_stage_index)
        stage.start(name)

        self.last_stage_index += 1

        try:
            yield stage
        finally:
            stage.finish("completed")
