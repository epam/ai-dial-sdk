import copy
from collections.abc import AsyncIterator, Callable, Coroutine, Mapping
from time import time
from typing import Any, Literal, Protocol, Self, TypeVar

from aidial_sdk._errors import to_dial_exception
from aidial_sdk.deployment.from_request_mixin import get_client_deployment_id
from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.responses import events
from aidial_sdk.responses._context import _ResponseContext
from aidial_sdk.responses._errors import map_exception
from aidial_sdk.responses._ids import RESPONSE_PREFIX, new_id
from aidial_sdk.responses._item_base import _ItemBuilder
from aidial_sdk.responses.enums import (
    ErrorCode,
    IncompleteReason,
    ResponseStatus,
)
from aidial_sdk.responses.events import Event
from aidial_sdk.responses.message import Message, _Phase
from aidial_sdk.responses.models import (
    IncompleteDetails,
    InputTokensDetails,
    OutputTokensDetails,
    ResponseError,
    ResponseObject,
    Usage,
)
from aidial_sdk.responses.reasoning import Reasoning
from aidial_sdk.responses.request import Request
from aidial_sdk.responses.server_tool import ImageGeneration, WebSearch
from aidial_sdk.responses.tool_call import CustomToolCall, FunctionCall
from aidial_sdk.utils._cancel_scope import CancelScope
from aidial_sdk.utils.errors import runtime_error
from aidial_sdk.utils.logging import log_warning

_Producer = Callable[[Request, "Response"], Coroutine[Any, Any, Any]]

_BuilderT = TypeVar("_BuilderT", bound=_ItemBuilder[Any])

_IncompleteReason = (
    IncompleteReason | Literal["max_output_tokens", "content_filter"]
)

# The request parameters the response object echoes
_ECHOED_PARAMETERS = {
    "instructions",
    "max_output_tokens",
    "max_tool_calls",
    "metadata",
    "parallel_tool_calls",
    "prompt_cache_key",
    "reasoning",
    "safety_identifier",
    "temperature",
    "text",
    "tool_choice",
    "tools",
    "top_logprobs",
    "top_p",
    "truncation",
    "user",
}


class _Model(Protocol):
    def model_dump(
        self, *, mode: str, by_alias: bool, exclude_unset: bool
    ) -> dict[str, Any]: ...


class Response:
    """
    The root builder: the only handle a handler needs.

    The handler's lifetime is the response's lifetime, so the lifecycle
    events are emitted by the framework: `response.created` and
    `response.in_progress` right before the first event the handler
    produces, and the terminal event once it returns.
    """

    request: Request

    _ctx: _ResponseContext
    _items: list[_ItemBuilder[Any]]
    _default_message: Message | None
    _usage: Usage | None
    _incomplete_reason: IncompleteReason | None
    _headers: list[tuple[str, str]]
    _body: dict[str, Any] | None
    _exception: DIALException | None
    _raised_early: bool

    def __init__(self, request: Request):
        self.request = request

        self._ctx = _ResponseContext(
            ResponseObject(
                id=new_id(RESPONSE_PREFIX),
                created_at=int(time()),
                model=get_client_deployment_id(
                    request.deployment.headers,
                    request.deployment.deployment_id,
                ),
                # An absent parameter takes the default of the response object
                **request.model_dump(
                    mode="json", include=_ECHOED_PARAMETERS, exclude_none=True
                ),
            ),
            stream=request.stream,
        )
        self._items = []
        self._default_message = None
        self._usage = None
        self._incomplete_reason = None
        self._headers = []
        self._body = None
        self._exception = None
        self._raised_early = False

    @property
    def stream(self) -> bool:
        return self.request.stream

    @property
    def items(self) -> tuple[_ItemBuilder[Any], ...]:
        """The item builders, in creation order, i.e. by `output_index`."""
        return tuple(self._items)

    def append_text(self, text: str) -> Self:
        """Appends to the default message, creating one if there is none."""
        self._message().append_text(text)
        return self

    def append_refusal(self, refusal: str) -> Self:
        """Appends to the default message, creating one if there is none."""
        self._message().append_refusal(refusal)
        return self

    def set_usage(
        self,
        input_tokens: int,
        output_tokens: int,
        *,
        cached_tokens: int = 0,
        cache_write_tokens: int = 0,
        reasoning_tokens: int = 0,
    ) -> Self:
        """No event: the usage is carried by the terminal event only."""
        self._check_not_finished('set "usage"')
        if self._usage is not None:
            raise runtime_error('Trying to set "usage" twice')

        self._usage = Usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            input_tokens_details=InputTokensDetails(
                cached_tokens=cached_tokens,
                cache_write_tokens=cache_write_tokens,
            ),
            output_tokens_details=OutputTokensDetails(
                reasoning_tokens=reasoning_tokens
            ),
        )
        return self

    def set_incomplete(self, reason: _IncompleteReason) -> Self:
        """
        Ends the response with `response.incomplete` instead of
        `response.completed`: for generation stopping early,
        not for a failure.
        """
        self._check_not_finished("set the response incomplete")
        self._incomplete_reason = IncompleteReason(reason)
        return self

    def error(
        self, code: ErrorCode, message: str, param: str | None = None
    ) -> Self:
        """
        Emits a stream-level `error` event. Not terminal, and not recorded
        in the response object: use `fail` to end the response.

        In block mode the event is dropped with a warning logged, since the
        response object has no place for it. Generation starts all the same.
        """
        self._check_not_finished("emit an error")
        self._ctx.start_generation()
        if not self.stream:
            log_warning(
                "The error event is dropped: the response isn't streamed"
            )
        self._ctx.emit(
            events.error(code=ErrorCode(code), message=message, param=param)
        )
        return self

    def fail(self, code: ErrorCode, message: str) -> Self:
        """
        Ends the response: emits `error`, then `response.failed`.

        The open items are treated as on an exception: a web search or an
        image generation is closed with `status: "failed"`, any other item
        is left open. Nothing can be written afterwards.
        """
        self._check_not_finished("fail the response")
        self._fail(ErrorCode(code), message)
        return self

    def unsafe_emit(self, event: Mapping[str, Any] | _Model) -> None:
        """
        The escape hatch: writes a raw event to the wire with only
        `sequence_number` filled in. A pydantic model is dumped the way
        openai's `to_dict()` does it, i.e. without the unset fields.

        It bypasses all the bookkeeping. The response object never sees
        the event, so an item it describes never appears in `output[]`,
        and the terminal event will disagree with the stream a client has
        just consumed. `output_index` / `content_index` are the caller's
        to get right, and no ordering invariant is checked.

        It exists for an event type newer than this SDK, and for
        a sequence the builders can't express, e.g. an upstream Responses
        stream proxied verbatim.

        In block mode it's a no-op that logs a warning: there is no stream
        to write to, and the response object can't absorb the event.
        Generation starts all the same, so that the setters' guard rails
        behave alike in both modes.
        """
        self._check_not_finished("emit an event")
        self._ctx.start_generation()
        if not self.stream:
            log_warning(
                "The event passed to unsafe_emit is dropped: "
                "the response isn't streamed"
            )
            return

        if isinstance(event, Mapping):
            raw = copy.deepcopy(dict(event))
        else:
            raw = event.model_dump(
                mode="json", by_alias=True, exclude_unset=True
            )

        self._ctx.emit(raw)

    def set_response_id(self, response_id: str) -> Self:
        if self._ctx.generation_started:
            raise runtime_error(
                'Trying to set "response_id" after start of generation'
            )

        self._ctx.response_object.id = response_id
        return self

    def set_created(self, created: int) -> Self:
        if self._ctx.generation_started:
            raise runtime_error(
                'Trying to set "created" after start of generation'
            )

        self._ctx.response_object.created_at = created
        return self

    def set_model(self, model: str) -> Self:
        if self._ctx.generation_started:
            raise runtime_error(
                'Trying to set "model" after start of generation'
            )

        self._ctx.response_object.model = model
        return self

    def append_header(self, key: str, value: str) -> Self:
        if self._ctx.generation_started and self.stream:
            raise runtime_error(
                "Trying to set a header after start of generation"
            )

        self._headers.append((key, value))
        return self

    async def aflush(self) -> None:
        """Waits until every event emitted so far is written."""
        await self._ctx._queue.join()

    def create_message(self, *, phase: _Phase | None = None) -> Message:
        return self._add_item(lambda: Message(self._ctx, phase))

    def create_reasoning(self) -> Reasoning:
        return self._add_item(lambda: Reasoning(self._ctx))

    def create_function_call(
        self, name: str, *, call_id: str | None = None
    ) -> FunctionCall:
        return self._add_item(lambda: FunctionCall(self._ctx, name, call_id))

    def create_custom_tool_call(
        self, name: str, *, call_id: str | None = None
    ) -> CustomToolCall:
        return self._add_item(lambda: CustomToolCall(self._ctx, name, call_id))

    def create_web_search(self) -> WebSearch:
        return self._add_item(lambda: WebSearch(self._ctx))

    def create_image_generation(self) -> ImageGeneration:
        return self._add_item(lambda: ImageGeneration(self._ctx))

    def _message(self) -> Message:
        message = self._default_message
        if message is None or message.closed:
            message = self._default_message = self.create_message()
        return message

    def _add_item(self, create: Callable[[], _BuilderT]) -> _BuilderT:
        self._check_not_finished("create an item")
        # The preamble goes first, before the item joins the response object
        self._ctx.start_generation()
        item = create()
        self._items.append(item)
        return item

    async def _generate_stream(
        self, producer: _Producer
    ) -> AsyncIterator[Event | DIALException]:
        """
        Runs the handler and yields its events as they are emitted.

        An exception the handler raised before producing any event is
        yielded right after the preamble, ahead of its failure events,
        so that the transport can answer with it instead.
        """
        queue = self._ctx._queue

        async with CancelScope() as cs:
            cs.create_task(self._run_producer(producer))

            # Nothing is emitted after the terminal event
            while not (self._ctx.finished and queue.empty()):
                event = await queue.get()
                queue.task_done()
                yield event

                # Set before an early failure emits the preamble, and never
                # once the handler has emitted it: settled by now either way
                if (
                    event["type"] == "response.in_progress"
                    and self._raised_early
                    and self._exception is not None
                ):
                    yield self._exception

    async def _generate_block(self, producer: _Producer) -> dict[str, Any]:
        """
        Runs the handler and returns the response object. Nothing has
        reached the client, so an exception the handler raised is answered
        as is.
        """
        await self._run_producer(producer)
        if self._exception is not None:
            raise self._exception.to_fastapi_exception()

        assert self._body is not None
        return self._body

    async def _run_producer(self, producer: _Producer) -> None:
        try:
            await producer(self.request, self)
        except Exception as e:
            exception = to_dial_exception(e)
            # Kept for the transport: when nothing reached the client yet,
            # it answers with this error instead,
            # unless the handler had already failed the response itself
            if not self._ctx.finished:
                self._exception = exception
                self._raised_early = not self._ctx.generation_started
            self._fail(*map_exception(exception))
        else:
            self._finish()

    def _check_not_finished(self, action: str) -> None:
        if self._ctx.finished:
            raise runtime_error(f"Trying to {action} after end of generation")

    def _finish(self) -> None:
        if self._ctx.finished:
            return

        self._ctx.start_generation()

        # In creation order, so that the transcript is deterministic.
        # On an incomplete response an item still open was cut off too,
        # which only these types can state
        for item in self._items:
            if not item.closed:
                if self._incomplete_reason is not None and isinstance(
                    item, Message | Reasoning | FunctionCall
                ):
                    item.set_incomplete()
                item._close_self()

        response_object = self._ctx.response_object
        response_object.usage = self._usage

        if self._incomplete_reason is None:
            response_object.status = ResponseStatus.COMPLETED
            self._terminate(events.response_completed(response=response_object))
        else:
            response_object.status = ResponseStatus.INCOMPLETE
            response_object.incomplete_details = IncompleteDetails(
                reason=self._incomplete_reason
            )
            self._terminate(
                events.response_incomplete(response=response_object)
            )

    def _fail(self, code: ErrorCode, message: str) -> None:
        # Already finished when the handler raises after `fail`
        if self._ctx.finished:
            return

        self._ctx.start_generation()

        # An item records the failure if it can, or is left open
        for item in self._items:
            if not item.closed:
                item._fail_self()

        self._ctx.emit(events.error(code=code, message=message))

        response_object = self._ctx.response_object
        # The tokens were used all the same
        response_object.usage = self._usage
        response_object.status = ResponseStatus.FAILED
        response_object.error = ResponseError(code=code, message=message)
        self._terminate(events.response_failed(response=response_object))

    def _terminate(self, terminal_event: Event) -> None:
        # The block body is the terminal event's payload,
        # so that the two modes agree by construction
        self._body = terminal_event["response"]
        self._ctx.finish(terminal_event)
