import asyncio
from time import time
from typing import Any, AsyncGenerator, Callable, Coroutine, Optional
from uuid import uuid4

from fastapi import HTTPException

from aidial_sdk.chat_completion.chunks import (
    BaseChunk,
    EndChoiceChunk,
    EndChunk,
    UsageChunk,
    UsagePerModelChunk,
)
from aidial_sdk.chat_completion.request import ChatCompletionRequest
from aidial_sdk.choice import Choice, SingleChoice
from aidial_sdk.exceptions import DIALException
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

    async def _generate_stream(self) -> AsyncGenerator[Any, None]:
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

        self._queue.task_done()

        last_end_choice_chunk = None
        usage_chunk = {}
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
                    usage_chunk = merge_recursive(
                        usage_chunk, item.to_dict(), path=[]
                    )
                else:
                    last_end_choice_chunk = merge_recursive(
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
                    chunk = merge_recursive(
                        last_end_choice_chunk, usage_chunk, []
                    )

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

                self._queue.task_done()

                return

            self._queue.task_done()

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
            try:
                self.user_task.result()
            except DIALException as e:
                raise HTTPException(
                    status_code=e.status_code,
                    detail={
                        "message": e.message,
                        "type": e.type,
                        "param": e.param,
                        "code": e.code,
                    },
                )
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail={
                        "message": e,
                        "type": "runtime_error",
                        "param": None,
                        "code": None,
                    },
                )

        self.first_chunk = (
            get_task.result() if get_task in done else await get_task
        )

    def choice(self) -> Choice:
        choice = Choice(self._queue, self._last_choice_index)
        self._last_choice_index += 1

        return choice

    def single_choice(self) -> SingleChoice:
        choice = SingleChoice(self._queue, self._last_choice_index)
        self._last_choice_index += 1

        return choice

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

    async def aflush(self):
        await self._queue.join()
