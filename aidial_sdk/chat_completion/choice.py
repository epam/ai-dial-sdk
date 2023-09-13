from asyncio import Queue
from types import TracebackType
from typing import Any, Optional, Type

from aidial_sdk.chat_completion.chunks import (
    AttachmentChunk,
    ContentChunk,
    EndChoiceChunk,
    StartChoiceChunk,
    StateChunk,
)
from aidial_sdk.chat_completion.enums import FinishReason
from aidial_sdk.chat_completion.stage import Stage


class Choice:
    _queue: Queue
    index: int
    last_attachment_index: int
    last_stage_index: int
    closed: bool
    state_submitted: bool

    def __init__(self, queue: Queue, choice_index: int):
        self._queue = queue
        self.index = choice_index
        self.last_attachment_index = 0
        self.last_stage_index = 0
        self.closed = False
        self.state_submitted = False

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
        else:
            self.close()
        return False

    def append_content(self, content: str) -> None:
        self._queue.put_nowait(ContentChunk(content, self.index))

    def add_attachment(
        self,
        type: Optional[str] = None,
        title: Optional[str] = None,
        data: Optional[str] = None,
        url: Optional[str] = None,
        reference_url: Optional[str] = None,
        reference_type: Optional[str] = None,
    ) -> None:
        self._queue.put_nowait(
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

    def append_state(self, state: Any) -> None:
        if self.state_submitted:
            # TODO: Generate exception
            return

        self._queue.put_nowait(StateChunk(self.index, state))
        self.state_submitted = True

    def create_stage(self, name: str) -> Stage:
        stage = Stage(self._queue, self.index, self.last_stage_index, name)
        self.last_stage_index += 1

        return stage

    def single_choice(
        self,
    ):
        pass

    def open(self):
        self._queue.put_nowait(StartChoiceChunk(choice_index=self.index))

    def close(self, finish_reason: FinishReason = FinishReason.STOP) -> None:
        if self.closed:
            # TODO: Generate exception
            return

        self.closed = True
        self._queue.put_nowait(EndChoiceChunk(finish_reason, self.index))
