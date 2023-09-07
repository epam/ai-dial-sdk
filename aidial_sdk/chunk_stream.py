import asyncio
from contextlib import contextmanager
from time import time
from typing import Any, Callable, Coroutine, Optional
from uuid import uuid4

from aidial_sdk.chat_completion.chunks import (
    BaseChunk,
    EndChoiceChunk,
    EndChunk,
    StartChoiceChunk,
    UsageChunk,
    UsagePerModelChunk,
)
from aidial_sdk.chat_completion.request import ChatCompletionRequest
from aidial_sdk.choice import Choice
from aidial_sdk.utils.merge_chunks import merge_recursive
from aidial_sdk.utils.streaming import (
    DONE_CHUNK,
    add_default_fields,
    generate_chunk,
)


class ChunkStream:
    _queue: asyncio.Queue
    _last_choice_index: int
    _last_usage_per_model_index: int

    request: ChatCompletionRequest
    response_id: str
    model: Optional[str]
    created: int

    def __init__(self, request: ChatCompletionRequest):
        self._queue = asyncio.Queue()
        self._last_choice_index = 0
        self._last_usage_per_model_index = 0

        self.request = request
        self.response_id = str(uuid4())
        self.model = None
        self.created = int(time())

    async def _generate_stream(self):
        chunk = self.first_chunk.to_dict()
        add_default_fields(
            chunk,
            self.response_id,
            self.model,
            self.created,
            "chat.completion.chunk"
            if self.request.stream
            else "chat.completion",
        )

        if self.request.stream:
            yield generate_chunk(chunk)
        else:
            yield chunk
        user_task_finished = False

        last_end_choice_chunk = None
        while True:
            get_task = asyncio.create_task(self._queue.get())
            done, pending = await asyncio.wait(
                [get_task, self.user_task], return_when=asyncio.FIRST_COMPLETED
            )
            if self.user_task in done:
                if not user_task_finished:
                    try:
                        self.user_task.result()
                    except Exception as e:
                        if self.request.stream:
                            pass
                        else:
                            pass

                    user_task_finished = True
                    self._queue.put_nowait(EndChunk())
            item = get_task.result() if get_task in done else await get_task

            if isinstance(item, EndChoiceChunk):
                if item.index == (self.request.n or 1) - 1:
                    last_end_choice_chunk = item.to_dict()
                    continue

            if isinstance(
                item,
                (UsageChunk, UsagePerModelChunk),
            ):
                if last_end_choice_chunk == None:
                    pass  # TODO

                chunk = merge_recursive(
                    last_end_choice_chunk, item.to_dict(), path=[]
                )
            elif isinstance(item, BaseChunk):
                chunk = item.to_dict()

                if self.request.stream:
                    add_default_fields(
                        chunk,
                        self.response_id,
                        self.model,
                        self.created,
                        "chat.completion.chunk",
                    )
                    yield generate_chunk(chunk)
                else:
                    yield chunk
            elif isinstance(item, EndChunk):
                if last_end_choice_chunk:
                    chunk = last_end_choice_chunk

                    if self.request.stream:
                        add_default_fields(
                            chunk,
                            self.response_id,
                            self.model,
                            self.created,
                            "chat.completion.chunk",
                        )
                        yield generate_chunk(chunk)
                    else:
                        yield chunk

                if self.request.stream:
                    yield DONE_CHUNK
                return

    async def _generator(
        self,
        producer: Callable[[Any, Any], Coroutine[Any, Any, Any]],
        request: ChatCompletionRequest,
    ):
        self.user_task = asyncio.create_task(producer(self, request))

        get_task = asyncio.create_task(self._queue.get())
        done, pending = await asyncio.wait(
            [get_task, self.user_task], return_when=asyncio.FIRST_COMPLETED
        )
        if self.user_task in done:
            self.user_task.result()

        self.first_chunk = (
            get_task.result() if get_task in done else await get_task
        )

    @contextmanager
    def choice(self):
        choice = Choice(self._queue, self._last_choice_index)
        self._queue.put_nowait(
            StartChoiceChunk(choice_index=self._last_choice_index)
        )
        self._last_choice_index += 1

        try:
            yield choice
        finally:
            self._queue.put_nowait(EndChoiceChunk(index=choice.index))

    def usage_per_model(
        self, model: str, prompt_tokens: int = 0, completion_tokens: int = 0
    ):
        if self.request.n != self._last_choice_index:
            pass  # TODO:

        self._queue.put_nowait(
            UsagePerModelChunk(
                self._last_usage_per_model_index,
                model,
                prompt_tokens,
                completion_tokens,
            )
        )
        self._last_usage_per_model_index += 1

    def usage(self, prompt_tokens: int = 0, completion_tokens: int = 0):
        if self.request.n != self._last_choice_index:
            pass  # TODO:

        self._queue.put_nowait(UsageChunk(prompt_tokens, completion_tokens))
