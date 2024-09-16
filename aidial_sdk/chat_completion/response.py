import asyncio
from time import time
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Coroutine,
    List,
    Union,
)
from uuid import uuid4

from aidial_sdk.chat_completion.choice import Choice
from aidial_sdk.chat_completion.chunks import (
    ArbitraryChunk,
    BaseChunk,
    DefaultChunk,
    DiscardedMessagesChunk,
    EndChoiceChunk,
    EndMarker,
    UsageChunk,
    UsagePerModelChunk,
)
from aidial_sdk.chat_completion.request import Request
from aidial_sdk.chat_completion.snapshot import StreamingResponseSnapshot
from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.exceptions import RequestValidationError, RuntimeServerError
from aidial_sdk.utils.errors import RUNTIME_ERROR_MESSAGE, runtime_error
from aidial_sdk.utils.logging import log_error, log_exception
from aidial_sdk.utils.merge_chunks import merge
from aidial_sdk.utils.streaming import DONE_MARKER, format_chunk


class Response:
    request: Request

    _queue: asyncio.Queue
    _snapshot: StreamingResponseSnapshot

    _last_choice_index: int
    _last_usage_per_model_index: int
    _generation_started: bool
    _discarded_messages_generated: bool
    _usage_generated: bool

    _default_chunk: DefaultChunk

    def __init__(self, request: Request):
        self._queue = asyncio.Queue()
        self._snapshot = StreamingResponseSnapshot()
        self._last_choice_index = 0
        self._last_usage_per_model_index = 0
        self._generation_started = False
        self._discarded_messages_generated = False
        self._usage_generated = False

        self.request = request

        self._default_chunk = DefaultChunk(
            response_id=str(uuid4()),
            model=None,
            created=int(time()),
            object=(
                "chat.completion.chunk" if request.stream else "chat.completion"
            ),
        )

    def get_block_response(self) -> dict:
        return self._snapshot.to_block_response()

    async def _generate_stream(
        self, first_chunk: BaseChunk
    ) -> AsyncGenerator[Any, None]:
        chunk = first_chunk.to_dict()

        if self.request.stream:
            yield format_chunk(chunk)
        else:
            yield chunk

        self._queue.task_done()

        user_task_finished = False

        last_end_choice_chunk = None
        usage_chunk = {}

        while True:
            get_task = asyncio.create_task(self._queue.get())
            done = (
                await asyncio.wait(
                    [get_task, self.user_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
            )[0]
            if self.user_task in done:
                if not user_task_finished:
                    end_chunk_generated = False
                    try:
                        self.user_task.result()
                    except DIALException as e:
                        if self.request.stream:
                            self.send_chunk(EndMarker(e))
                            end_chunk_generated = True
                        else:
                            raise e.to_fastapi_exception()
                    except Exception as e:
                        log_exception(RUNTIME_ERROR_MESSAGE)

                        if self.request.stream:
                            self.send_chunk(EndMarker(e))
                            end_chunk_generated = True
                        else:
                            raise RuntimeServerError(
                                RUNTIME_ERROR_MESSAGE
                            ).to_fastapi_exception()

                    if not end_chunk_generated:
                        self.send_chunk(EndMarker())
                    user_task_finished = True

            item = get_task.result() if get_task in done else await get_task

            if isinstance(item, EndChoiceChunk):
                if item.choice_index == (self.request.n or 1) - 1:
                    last_end_choice_chunk = item.to_dict()
                    self._queue.task_done()
                    continue

            if isinstance(
                item,
                (UsageChunk, UsagePerModelChunk, DiscardedMessagesChunk),
            ):
                usage_chunk = merge(usage_chunk, item.to_dict())

            elif isinstance(item, BaseChunk):
                chunk = item.to_dict()

                if self.request.stream:
                    yield format_chunk(chunk)
                else:
                    yield chunk

            elif isinstance(item, EndMarker):
                if last_end_choice_chunk:
                    chunk = merge(last_end_choice_chunk, usage_chunk)

                    if self.request.stream:
                        yield format_chunk(chunk)
                    else:
                        yield chunk

                if item.exc:
                    if isinstance(item.exc, DIALException):
                        chunk = item.exc.json_error()
                    else:
                        chunk = format_chunk(
                            RuntimeServerError(
                                RUNTIME_ERROR_MESSAGE
                            ).json_error()
                        )
                    yield chunk
                else:
                    if self._last_choice_index != (self.request.n or 1):
                        log_error("Not all choices were generated")

                        error = RuntimeServerError(RUNTIME_ERROR_MESSAGE)

                        if self.request.stream:
                            yield format_chunk(error.json_error())
                        else:
                            raise error.to_fastapi_exception()

                if self.request.stream:
                    yield format_chunk(DONE_MARKER)

                self._queue.task_done()
                return

            self._queue.task_done()

    async def _generator(
        self,
        producer: Callable[[Request, "Response"], Coroutine[Any, Any, Any]],
        request: Request,
    ) -> BaseChunk:
        self.user_task = asyncio.create_task(producer(request, self))

        get_task = asyncio.create_task(self._queue.get())
        done = (
            await asyncio.wait(
                [get_task, self.user_task], return_when=asyncio.FIRST_COMPLETED
            )
        )[0]
        if self.user_task in done:
            try:
                self.user_task.result()
            except DIALException as e:
                raise e.to_fastapi_exception()
            except Exception:
                log_exception(RUNTIME_ERROR_MESSAGE)
                raise RuntimeServerError(
                    RUNTIME_ERROR_MESSAGE
                ).to_fastapi_exception()

        return get_task.result() if get_task in done else await get_task

    def create_choice(self) -> Choice:
        self._generation_started = True

        if self._last_choice_index >= (self.request.n or 1):
            raise runtime_error("Trying to generate more chunks than requested")

        choice = Choice(self, self._last_choice_index)
        self._last_choice_index += 1

        return choice

    def create_single_choice(self) -> Choice:
        if self._last_choice_index > 0:
            raise runtime_error(
                "Trying to generate a single choice after choice"
            )
        if (self.request.n or 1) > 1:
            raise RequestValidationError(
                message=f"{self.request.deployment_id} deployment doesn't support n > 1"
            )

        return self.create_choice()

    def add_usage_per_model(
        self, model: str, prompt_tokens: int = 0, completion_tokens: int = 0
    ):
        self._generation_started = True

        if self._last_choice_index != (self.request.n or 1):
            raise runtime_error(
                'Trying to set "usage_per_model" before generating all choices',
            )

        self.send_chunk(
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
        if self._last_choice_index != (self.request.n or 1):
            raise runtime_error(
                'Trying to set "discarded_messages" before generating all choices',
            )

        self._discarded_messages_generated = True
        self.send_chunk(DiscardedMessagesChunk(discarded_messages))

    def set_usage(self, prompt_tokens: int = 0, completion_tokens: int = 0):
        self._generation_started = True

        if self._usage_generated:
            raise runtime_error('Trying to set "usage" twice')
        if self._last_choice_index != (self.request.n or 1):
            raise runtime_error(
                'Trying to set "usage" before generating all choices',
            )

        self._usage_generated = True
        self.send_chunk(UsageChunk(prompt_tokens, completion_tokens))

    def send_chunk(self, chunk: Union[BaseChunk, EndMarker]):
        # FIXME: ugly hack
        if isinstance(chunk, ArbitraryChunk):
            for choice in chunk.data.choices:
                self._last_choice_index = max(
                    self._last_choice_index, choice.index + 1
                )

        if isinstance(chunk, BaseChunk):
            self._snapshot.add_delta(chunk.to_dict(self._default_chunk.dict()))

        self._queue.put_nowait(chunk)

    async def aflush(self):
        await self._queue.join()

    def set_created(self, created: int):
        if self._generation_started:
            raise runtime_error(
                'Trying to set "created" after start of generation'
            )

        self._created = created

    def set_model(self, model: str):
        if self._generation_started:
            raise runtime_error(
                'Trying to set "model" after start of generation'
            )

        self._model = model

    def set_response_id(self, response_id: str):
        if self._generation_started:
            raise runtime_error(
                'Trying to set "response_id" after start of generation',
            )

        self._response_id = response_id
