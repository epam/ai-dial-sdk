import asyncio
from typing import (
    Any,
    Callable,
    Coroutine,
)
from contextlib import contextmanager
from dialsdk.choice import Choice
from dialsdk.chat_completion.chunks import (
    DIALChatCompletionInit,
    DIALChatCompletionEndChunk,
    DIALChatCompletionStartChoiceChunk,
    DIALChatCompletionEndChoiceChunk,
    DIALChatCompletionUsageChunk,
    DIALChatCompletionUsagePerModelChunk
)
from uuid import uuid4
from dialsdk.chat_completion.request import ChatCompletionRequest


class ChunkStream:
    queue: asyncio.Queue
    last_choice_index: int

    def __init__(self):
        self.queue = asyncio.Queue()
        self.last_choice_index = 0

    async def generator(
        self,
        producer: Callable[[Any], Coroutine[Any, Any, Any]],
        request: ChatCompletionRequest,
    ):
        task = asyncio.create_task(producer(self, request))

        get_task = asyncio.create_task(self.queue.get())
        done, pending = await asyncio.wait(
            [get_task, task], return_when=asyncio.FIRST_COMPLETED
        )
        if task in done:
            task.result()
        item = get_task.result() if get_task in done else await get_task
        return [task, self.queue, item]

    @contextmanager
    def choice(self):
        choice = Choice(self.queue, self.last_choice_index)
        self.queue.put_nowait(
            DIALChatCompletionStartChoiceChunk(choice_index=self.last_choice_index)
        )
        self.last_choice_index += 1

        try:
            yield choice
        finally:
            self.queue.put_nowait(DIALChatCompletionEndChoiceChunk(index=choice.index))

    @contextmanager
    def usage_per_model(self, model_name: str, prompt_tokens: int, completion_tokens: int):
        choice = Choice(self.queue, self.last_choice_index)
        DIALChatCompletionUsagePerModelChunk(choice_index=self.last_choice_index)
        try:
            yield choice
        finally:
            self.queue.put_nowait(DIALChatCompletionEndChoiceChunk(index=choice.index))

    @contextmanager
    def stream(self, response_id: str = None, model: str = None):
        if not response_id:
            response_id = str(uuid4())

        self.queue.put_nowait(DIALChatCompletionInit(response_id, model))

        try:
            yield self
        finally:
            self.queue.put_nowait(DIALChatCompletionEndChunk())

    def usage(self, prompt_tokens: int = 0, completion_tokens: int = 0):
        self.queue.put_nowait(
            DIALChatCompletionUsageChunk(prompt_tokens, completion_tokens)
        )
