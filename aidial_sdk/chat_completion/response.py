import asyncio
from time import time
from typing import Any, Callable, Coroutine, List
from uuid import uuid4

from typing_extensions import assert_never

from aidial_sdk.chat_completion._types import ChunkQueue
from aidial_sdk.chat_completion.choice import Choice
from aidial_sdk.chat_completion.chunks import (
    ArbitraryChunk,
    BaseChunk,
    BaseChunkWithDefaults,
    DefaultChunk,
    DiscardedMessagesChunk,
    EndChoiceChunk,
    EndChunk,
    ExceptionChunk,
    UsageChunk,
    UsagePerModelChunk,
)
from aidial_sdk.chat_completion.request import Request
from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.exceptions import RequestValidationError, RuntimeServerError
from aidial_sdk.utils.errors import RUNTIME_ERROR_MESSAGE, runtime_error
from aidial_sdk.utils.logging import log_error, log_exception
from aidial_sdk.utils.merge_chunks import merge
from aidial_sdk.utils.streaming import ResponseStream


class Response:
    request: Request

    _queue: ChunkQueue
    _last_choice_index: int
    _last_usage_per_model_index: int
    _generation_started: bool
    _discarded_messages_generated: bool
    _usage_generated: bool

    _default_chunk: DefaultChunk

    def __init__(self, request: Request):
        self._queue = asyncio.Queue()
        self._last_choice_index = 0
        self._last_usage_per_model_index = 0
        self._generation_started = False
        self._discarded_messages_generated = False
        self._usage_generated = False

        self.request = request

        self._default_chunk = DefaultChunk(
            id=str(uuid4()),
            created=int(time()),
            object=(
                "chat.completion.chunk"
                if self.request.stream
                else "chat.completion"
            ),
        )

    @property
    def n(self) -> int:
        return self.request.n or 1

    @property
    def stream(self) -> int:
        return self.request.stream

    async def _generate_stream(
        self,
        producer: Callable[[Request, "Response"], Coroutine[Any, Any, Any]],
    ) -> ResponseStream:

        def _create_chunk(chunk):
            return BaseChunkWithDefaults(
                chunk=chunk, defaults=self._default_chunk
            )

        user_task = asyncio.create_task(producer(self.request, self))
        user_task_is_done = False

        # A list of chunks whose emitting is delayed up until the very last moment
        delayed_chunks: List[BaseChunk] = []

        while True:
            get_chunk_task = asyncio.create_task(self._queue.get())
            done = (
                await asyncio.wait(
                    [get_chunk_task, user_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
            )[0]

            if user_task in done and not user_task_is_done:
                user_task_is_done = True
                try:
                    user_task.result()
                except Exception as e:
                    if isinstance(e, DIALException):
                        dial_exception = e
                    else:
                        log_exception(RUNTIME_ERROR_MESSAGE)
                        dial_exception = RuntimeServerError(
                            RUNTIME_ERROR_MESSAGE
                        )

                    self._queue.put_nowait(ExceptionChunk(dial_exception))
                else:
                    self._queue.put_nowait(EndChunk())

            chunk = await get_chunk_task
            self._queue.task_done()

            if isinstance(chunk, BaseChunk):

                is_last_end_choice_chunk = (
                    isinstance(chunk, EndChoiceChunk)
                    and chunk.choice_index == self.n - 1
                )

                is_top_level_chunk = isinstance(
                    chunk,
                    (UsageChunk, UsagePerModelChunk, DiscardedMessagesChunk),
                )

                if is_last_end_choice_chunk or is_top_level_chunk:
                    delayed_chunks.append(chunk)
                else:
                    yield _create_chunk(chunk)

            elif isinstance(chunk, (ExceptionChunk, EndChunk)):
                if delayed_chunks:
                    final_chunk = merge(*[d.to_dict() for d in delayed_chunks])
                    yield _create_chunk(ArbitraryChunk(chunk=final_chunk))

                if isinstance(chunk, ExceptionChunk):
                    yield chunk.exc
                elif isinstance(chunk, EndChunk):
                    if self._last_choice_index != self.n:
                        log_error("Not all choices were generated")
                        yield RuntimeServerError(RUNTIME_ERROR_MESSAGE)
                else:
                    assert_never(chunk)

                return

            else:
                assert_never(chunk)

    def create_choice(self) -> Choice:
        self._generation_started = True

        if self._last_choice_index >= self.n:
            raise runtime_error("Trying to generate more chunks than requested")

        choice = Choice(self._queue, self._last_choice_index)
        self._last_choice_index += 1

        return choice

    def create_single_choice(self) -> Choice:
        if self._last_choice_index > 0:
            raise runtime_error(
                "Trying to generate a single choice after choice"
            )
        if self.n > 1:
            raise RequestValidationError(
                message=f"{self.request.deployment_id} deployment doesn't support n > 1"
            )

        return self.create_choice()

    def add_usage_per_model(
        self, model: str, prompt_tokens: int = 0, completion_tokens: int = 0
    ):
        self._generation_started = True

        if self._last_choice_index != self.n:
            raise runtime_error(
                'Trying to set "usage_per_model" before generating all choices',
            )

        self._queue.put_nowait(
            UsagePerModelChunk(
                self._last_usage_per_model_index,
                model,
                prompt_tokens,
                completion_tokens,
            )
        )
        self._last_usage_per_model_index += 1

    def set_discarded_messages(self, discarded_messages: List[int]):
        self._generation_started = True

        if self._discarded_messages_generated:
            raise runtime_error('Trying to set "discarded_messages" twice')
        if self._last_choice_index != self.n:
            raise runtime_error(
                'Trying to set "discarded_messages" before generating all choices',
            )

        self._discarded_messages_generated = True
        self._queue.put_nowait(DiscardedMessagesChunk(discarded_messages))

    def set_usage(self, prompt_tokens: int = 0, completion_tokens: int = 0):
        self._generation_started = True

        if self._usage_generated:
            raise runtime_error('Trying to set "usage" twice')
        if self._last_choice_index != self.n:
            raise runtime_error(
                'Trying to set "usage" before generating all choices',
            )

        self._usage_generated = True
        self._queue.put_nowait(UsageChunk(prompt_tokens, completion_tokens))

    async def aflush(self):
        await self._queue.join()

    def set_created(self, created: int):
        if self._generation_started:
            raise runtime_error(
                'Trying to set "created" after start of generation'
            )

        self._default_chunk["created"] = created

    def set_model(self, model: str):
        if self._generation_started:
            raise runtime_error(
                'Trying to set "model" after start of generation'
            )

        self._default_chunk["model"] = model

    def set_response_id(self, response_id: str):
        if self._generation_started:
            raise runtime_error(
                'Trying to set "response_id" after start of generation',
            )

        self._default_chunk["id"] = response_id
