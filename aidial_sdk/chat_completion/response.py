import asyncio
import logging
from time import time
from traceback import format_exc
from typing import Any, AsyncGenerator, Callable, Coroutine, Optional
from uuid import uuid4

from fastapi import HTTPException

from aidial_sdk.chat_completion.choice import Choice
from aidial_sdk.chat_completion.chunks import (
    BaseChunk,
    EndChoiceChunk,
    EndChunk,
    UsageChunk,
    UsagePerModelChunk,
)
from aidial_sdk.chat_completion.request import ChatCompletionRequest
from aidial_sdk.exceptions import HTTPException as DialHttpException
from aidial_sdk.utils.merge_chunks import merge_recursive
from aidial_sdk.utils.streaming import (
    DONE_CHUNK,
    add_default_fields,
    format_chunk,
    json_error,
)


class ChatCompletionResponse:
    _queue: asyncio.Queue
    _last_choice_index: int
    _last_usage_per_model_index: int
    _generation_started: bool
    _usage_generated: bool

    request: ChatCompletionRequest
    response_id: str
    model: Optional[str]
    created: int

    def __init__(self, request: ChatCompletionRequest):
        self._queue = asyncio.Queue()
        self._last_choice_index = 0
        self._last_usage_per_model_index = 0
        self._generation_started = False
        self._usage_generated = False

        self.log = logging.getLogger(request.deployment_id)

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
            formatted_chunk = format_chunk(chunk)
            self.log.debug(formatted_chunk.strip())
            yield formatted_chunk
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
                    end_chunk_generated = False
                    try:
                        self.user_task.result()
                    except DialHttpException as e:
                        if self.request.stream:
                            self._queue.put_nowait(EndChunk(e))
                            end_chunk_generated = True
                        else:
                            raise HTTPException(
                                status_code=e.status_code,
                                detail=json_error(
                                    message=e.message,
                                    type=e.type,
                                    param=e.param,
                                    code=e.code,
                                ),
                            )
                    except Exception as e:
                        self.log.error(format_exc(limit=None, chain=True))

                        if self.request.stream:
                            self._queue.put_nowait(EndChunk(e))
                            end_chunk_generated = True
                        else:
                            raise HTTPException(
                                status_code=500,
                                detail=json_error(
                                    message="Error during processing the request",
                                    type="runtime_error",
                                ),
                            )

                    if not end_chunk_generated:
                        self._queue.put_nowait(EndChunk())
                    user_task_finished = True
            item = get_task.result() if get_task in done else await get_task

            if isinstance(item, EndChoiceChunk):
                if item.index == (self.request.n or 1) - 1:
                    last_end_choice_chunk = item.to_dict()
                    self._queue.task_done()
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
                    formatted_chunk = format_chunk(chunk)
                    self.log.debug(formatted_chunk.strip())
                    yield formatted_chunk
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
                        formatted_chunk = format_chunk(chunk)
                        self.log.debug(formatted_chunk.strip())
                        yield formatted_chunk
                    else:
                        yield chunk

                if item.exc:
                    if isinstance(item.exc, DialHttpException):
                        formatted_chunk = format_chunk(
                            json_error(
                                message=item.exc.message,
                                type=item.exc.type,
                                param=item.exc.param,
                                code=item.exc.code,
                            )
                        )
                    else:
                        formatted_chunk = format_chunk(
                            json_error(
                                message="Error during processing the request",
                                type="runtime_error",
                            )
                        )
                    self.log.debug(formatted_chunk.strip())
                    yield formatted_chunk
                else:
                    if self._last_choice_index != (self.request.n or 1):
                        self.log.error("Not all choices were generated")

                        error = json_error(
                            message="Error during processing the request",
                            type="runtime_error",
                        )

                        if self.request.stream:
                            formatted_chunk = format_chunk(error)
                            self.log.debug(formatted_chunk.strip())
                            yield formatted_chunk
                        else:
                            raise HTTPException(
                                status_code=500,
                                detail=error,
                            )

                if self.request.stream:
                    self.log.debug(DONE_CHUNK.strip())
                    yield DONE_CHUNK

                self._queue.task_done()

                return

            self._queue.task_done()

    def _runtime_error(self, reason):
        self.log.error(reason)

        raise DialHttpException(
            status_code=500,
            message="Error during processing the request",
            type="runtime_error",
        )

    async def _generator(
        self,
        producer: Callable[[Any, Any], Coroutine[Any, Any, Any]],
        request: ChatCompletionRequest,
    ):
        self.user_task = asyncio.create_task(producer(request, self))

        get_task = asyncio.create_task(self._queue.get())
        done, pending = await asyncio.wait(
            [get_task, self.user_task], return_when=asyncio.FIRST_COMPLETED
        )
        if self.user_task in done:
            try:
                self.user_task.result()
            except DialHttpException as e:
                raise HTTPException(
                    status_code=e.status_code,
                    detail=json_error(
                        message=e.message,
                        type=e.type,
                        param=e.param,
                        code=e.code,
                    ),
                )
            except Exception as e:
                self.log.error(format_exc(limit=None, chain=True))
                raise HTTPException(
                    status_code=500,
                    detail=json_error(
                        message="Error during processing the request",
                        type="runtime_error",
                    ),
                )

        self.first_chunk = (
            get_task.result() if get_task in done else await get_task
        )

    def create_choice(self) -> Choice:
        self._generation_started = True

        if self._last_choice_index >= (self.request.n or 1):
            self._runtime_error("Trying to generate more chunks than requested")

        choice = Choice(self._queue, self._last_choice_index)
        self._last_choice_index += 1

        return choice

    def create_single_choice(self) -> Choice:
        self._generation_started = True

        if self._last_choice_index > 0:
            self._runtime_error(
                "Trying to generate a signle choice after choice"
            )
        if (self.request.n or 1) > 1:
            raise DialHttpException(
                status_code=422,
                message=f"{self.request.deployment_id} deployment doesn't support n > 1",
                type="invalid_request_error",
            )

        choice = Choice(self._queue, self._last_choice_index)
        self._last_choice_index += 1

        return choice

    def add_usage_per_model(
        self, model: str, prompt_tokens: int = 0, completion_tokens: int = 0
    ):
        self._generation_started = True

        if self._last_choice_index != (self.request.n or 1):
            self._runtime_error(
                'Trying to set "usage_per_model" before generating of all choices'
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

    def set_usage(self, prompt_tokens: int = 0, completion_tokens: int = 0):
        self._generation_started = True

        if self._usage_generated:
            self._runtime_error('Trying to set "usage" twice')
        if self._last_choice_index != (self.request.n or 1):
            self._runtime_error(
                'Trying to set "usage" before generating of all choices'
            )

        self._usage_generated = True
        self._queue.put_nowait(UsageChunk(prompt_tokens, completion_tokens))

    async def aflush(self):
        await self._queue.join()

    def set_created(self, created: int):
        if self._generation_started:
            self._runtime_error(
                'Trying to set "created" after start of generation'
            )

        self.created = created

    def set_model(self, model: str):
        if self._generation_started:
            self._runtime_error(
                'Trying to set "model" after start of generation'
            )

        self.model = model

    def set_response_id(self, response_id: str):
        if self._generation_started:
            self._runtime_error(
                'Trying to set "response_id" after start of generation'
            )

        self.response_id = response_id
