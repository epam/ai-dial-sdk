import asyncio
from time import time
from typing import Any, AsyncGenerator, Callable, Coroutine, Dict, Optional
from uuid import uuid4

from fastapi import HTTPException

from aidial_sdk.chat_completion.choice import Choice
from aidial_sdk.chat_completion.chunks import (
    BaseChunk,
    DiscardedMessagesChunk,
    EndChoiceChunk,
    EndChunk,
    UsageChunk,
    UsagePerModelChunk,
)
from aidial_sdk.chat_completion.request import Request
from aidial_sdk.exceptions import HTTPException as DialHttpException
from aidial_sdk.utils.errors import json_error, runtime_error
from aidial_sdk.utils.logging import log_error, log_exception
from aidial_sdk.utils.merge_chunks import merge
from aidial_sdk.utils.streaming import DONE_MARKER, format_chunk


class Response:
    request: Request

    _queue: asyncio.Queue
    _last_choice_index: int
    _last_usage_per_model_index: int
    _generation_started: bool
    _discarded_messages_generated: bool
    _usage_generated: bool
    _response_id: str
    _model: Optional[str]
    _created: int

    def __init__(self, request: Request):
        self._queue = asyncio.Queue()
        self._last_choice_index = 0
        self._last_usage_per_model_index = 0
        self._generation_started = False
        self._discarded_messages_generated = False
        self._usage_generated = False

        self.request = request
        self._response_id = str(uuid4())
        self._model = None
        self._created = int(time())

    def _add_default_fields(self, target: Dict[str, Any]) -> None:
        target["id"] = self._response_id
        if self._model:
            target["model"] = self._model
        target["created"] = self._created
        target["object"] = (
            "chat.completion.chunk"
            if self.request.stream
            else "chat.completion"
        )

    async def _generate_stream(
        self, first_chunk: BaseChunk
    ) -> AsyncGenerator[Any, None]:
        chunk = first_chunk.to_dict()

        # NOTE: add default fields only to the first chunk in a non-streaming mode and to all chunks in a streaming mode
        self._add_default_fields(chunk)

        if self.request.stream:
            formatted_chunk = format_chunk(chunk)
            yield formatted_chunk
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
                        log_exception(e)

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
                    self._add_default_fields(chunk)
                    formatted_chunk = format_chunk(chunk)
                    yield formatted_chunk
                else:
                    yield chunk
            elif isinstance(item, EndChunk):
                if last_end_choice_chunk:
                    chunk = merge(last_end_choice_chunk, usage_chunk)

                    if self.request.stream:
                        self._add_default_fields(chunk)
                        formatted_chunk = format_chunk(chunk)
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
                    yield formatted_chunk
                else:
                    if self._last_choice_index != (self.request.n or 1):
                        log_error("Not all choices were generated")

                        error = json_error(
                            message="Error during processing the request",
                            type="runtime_error",
                        )

                        if self.request.stream:
                            formatted_chunk = format_chunk(error)
                            yield formatted_chunk
                        else:
                            raise HTTPException(
                                status_code=500,
                                detail=error,
                            )

                if self.request.stream:
                    yield format_chunk(DONE_MARKER)

                self._queue.task_done()

                return

            self._queue.task_done()

    async def _generator(
        self,
        producer: Callable[[Any, Any], Coroutine[Any, Any, Any]],
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
                log_exception(e)
                raise HTTPException(
                    status_code=500,
                    detail=json_error(
                        message="Error during processing the request",
                        type="runtime_error",
                    ),
                )

        return get_task.result() if get_task in done else await get_task

    def create_choice(self) -> Choice:
        self._generation_started = True

        if self._last_choice_index >= (self.request.n or 1):
            runtime_error("Trying to generate more chunks than requested")

        choice = Choice(self._queue, self._last_choice_index)
        self._last_choice_index += 1

        return choice

    def create_single_choice(self) -> Choice:
        if self._last_choice_index > 0:
            runtime_error("Trying to generate a single choice after choice")
        if (self.request.n or 1) > 1:
            raise DialHttpException(
                status_code=422,
                message=f"{self.request.deployment_id} deployment doesn't support n > 1",
                type="invalid_request_error",
            )

        return self.create_choice()

    def add_usage_per_model(
        self, model: str, prompt_tokens: int = 0, completion_tokens: int = 0
    ):
        self._generation_started = True

        if self._last_choice_index != (self.request.n or 1):
            runtime_error(
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

    def set_discarded_messages(self, discarded_messages: int):
        self._generation_started = True

        if self._discarded_messages_generated:
            runtime_error('Trying to set "discarded_messages" twice')
        if self._last_choice_index != (self.request.n or 1):
            runtime_error(
                'Trying to set "discarded_messages" before generating all choices',
            )

        self._discarded_messages_generated = True
        self._queue.put_nowait(DiscardedMessagesChunk(discarded_messages))

    def set_usage(self, prompt_tokens: int = 0, completion_tokens: int = 0):
        self._generation_started = True

        if self._usage_generated:
            runtime_error('Trying to set "usage" twice')
        if self._last_choice_index != (self.request.n or 1):
            runtime_error(
                'Trying to set "usage" before generating all choices',
            )

        self._usage_generated = True
        self._queue.put_nowait(UsageChunk(prompt_tokens, completion_tokens))

    async def aflush(self):
        await self._queue.join()

    def set_created(self, created: int):
        if self._generation_started:
            runtime_error('Trying to set "created" after start of generation')

        self._created = created

    def set_model(self, model: str):
        if self._generation_started:
            runtime_error('Trying to set "model" after start of generation')

        self._model = model

    def set_response_id(self, response_id: str):
        if self._generation_started:
            runtime_error(
                'Trying to set "response_id" after start of generation',
            )

        self._response_id = response_id
