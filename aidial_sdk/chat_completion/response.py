import asyncio
import json
import logging
from logging import Logger
from time import time
from typing import Any, AsyncGenerator, Callable, Coroutine, Dict, Optional
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
from aidial_sdk.utils.errors import json_error, runtime_error
from aidial_sdk.utils.merge_chunks import merge
from aidial_sdk.utils.streaming import DONE_CHUNK


class ChatCompletionResponse:
    request: ChatCompletionRequest

    _queue: asyncio.Queue
    _last_choice_index: int
    _last_usage_per_model_index: int
    _generation_started: bool
    _usage_generated: bool
    _log: Logger
    _response_id: str
    _model: Optional[str]
    _created: int
    _first_chunk: Optional[BaseChunk]

    def __init__(self, request: ChatCompletionRequest):
        self._queue = asyncio.Queue()
        self._last_choice_index = 0
        self._last_usage_per_model_index = 0
        self._generation_started = False
        self._usage_generated = False
        self._first_chunk = None

        self._log = logging.getLogger(request.deployment_id)

        self.request = request
        self._response_id = str(uuid4())
        self._model = None
        self._created = int(time())

    @staticmethod
    def _add_default_fields(
        target: Dict[str, Any],
        response_id: str,
        model: Optional[str],
        created: int,
        type: str,
    ) -> None:
        target["id"] = response_id
        if model:
            target["model"] = model
        target["created"] = created
        target["object"] = type

    def format_chunk(self, data: Any):
        data = "data: " + json.dumps(data, separators=(",", ":"))
        self._log.debug(data)
        return f"{data}\n\n"

    async def _generate_stream(self) -> AsyncGenerator[Any, None]:
        if self._first_chunk:
            chunk = self._first_chunk.dict()
            self._add_default_fields(
                chunk,
                self._response_id,
                self._model,
                self._created,
                "chat.completion.chunk"
                if self.request.stream
                else "chat.completion",
            )

            if self.request.stream:
                formatted_chunk = self.format_chunk(chunk)
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
                        self._log.exception(e)

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
                    last_end_choice_chunk = item.dict()
                    self._queue.task_done()
                    continue

            if isinstance(
                item,
                (UsageChunk, UsagePerModelChunk),
            ):
                if last_end_choice_chunk is None:
                    usage_chunk = merge(usage_chunk, item.dict())
                else:
                    last_end_choice_chunk = merge(
                        last_end_choice_chunk, item.dict()
                    )
            elif isinstance(item, BaseChunk):
                chunk = item.dict()

                if self.request.stream:
                    self._add_default_fields(
                        chunk,
                        self._response_id,
                        self._model,
                        self._created,
                        "chat.completion.chunk",
                    )
                    formatted_chunk = self.format_chunk(chunk)
                    yield formatted_chunk
                else:
                    yield chunk
            elif isinstance(item, EndChunk):
                if last_end_choice_chunk:
                    chunk = merge(last_end_choice_chunk, usage_chunk)

                    if self.request.stream:
                        self._add_default_fields(
                            chunk,
                            self._response_id,
                            self._model,
                            self._created,
                            "chat.completion.chunk",
                        )
                        formatted_chunk = self.format_chunk(chunk)
                        yield formatted_chunk
                    else:
                        yield chunk

                if item.exc:
                    if isinstance(item.exc, DialHttpException):
                        formatted_chunk = self.format_chunk(
                            json_error(
                                message=item.exc.message,
                                type=item.exc.type,
                                param=item.exc.param,
                                code=item.exc.code,
                            )
                        )
                    else:
                        formatted_chunk = self.format_chunk(
                            json_error(
                                message="Error during processing the request",
                                type="runtime_error",
                            )
                        )
                    yield formatted_chunk
                else:
                    if self._last_choice_index != (self.request.n or 1):
                        self._log.error("Not all choices were generated")

                        error = json_error(
                            message="Error during processing the request",
                            type="runtime_error",
                        )

                        if self.request.stream:
                            formatted_chunk = self.format_chunk(error)
                            yield formatted_chunk
                        else:
                            raise HTTPException(
                                status_code=500,
                                detail=error,
                            )

                if self.request.stream:
                    self._log.debug(DONE_CHUNK.strip())
                    yield DONE_CHUNK

                self._queue.task_done()

                return

            self._queue.task_done()

    async def _generator(
        self,
        producer: Callable[[Any, Any], Coroutine[Any, Any, Any]],
        request: ChatCompletionRequest,
    ):
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
                self._log.exception(e)
                raise HTTPException(
                    status_code=500,
                    detail=json_error(
                        message="Error during processing the request",
                        type="runtime_error",
                    ),
                )

        self._first_chunk = (
            get_task.result() if get_task in done else await get_task
        )

    def create_choice(self) -> Choice:
        self._generation_started = True

        if self._last_choice_index >= (self.request.n or 1):
            runtime_error(
                self._log, "Trying to generate more chunks than requested"
            )

        choice = Choice(self._queue, self._last_choice_index, self._log)
        self._last_choice_index += 1

        return choice

    def create_single_choice(self) -> Choice:
        if self._last_choice_index > 0:
            runtime_error(
                self._log, "Trying to generate a single choice after choice"
            )
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
                self._log,
                'Trying to set "usage_per_model" before generating of all choices',
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
            runtime_error(self._log, 'Trying to set "usage" twice')
        if self._last_choice_index != (self.request.n or 1):
            runtime_error(
                self._log,
                'Trying to set "usage" before generating of all choices',
            )

        self._usage_generated = True
        self._queue.put_nowait(UsageChunk(prompt_tokens, completion_tokens))

    async def aflush(self):
        await self._queue.join()

    def set_created(self, created: int):
        if self._generation_started:
            runtime_error(
                self._log, 'Trying to set "created" after start of generation'
            )

        self._created = created

    def set_model(self, model: str):
        if self._generation_started:
            runtime_error(
                self._log, 'Trying to set "model" after start of generation'
            )

        self._model = model

    def set_response_id(self, response_id: str):
        if self._generation_started:
            runtime_error(
                self._log,
                'Trying to set "response_id" after start of generation',
            )

        self._response_id = response_id
