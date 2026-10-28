import uuid
from collections.abc import (
    AsyncIterator,
    Callable,
    Hashable,
    Iterable,
    Iterator,
)
from typing import Literal, Protocol, TypeVar

import openai
from anthropic.types import (
    Message,
    RawContentBlockDeltaEvent,
    RawContentBlockStartEvent,
    RawContentBlockStopEvent,
    RawMessageDeltaEvent,
    RawMessageStartEvent,
    RawMessageStopEvent,
    StopReason,
    Usage,
)
from anthropic.types.message_delta_usage import MessageDeltaUsage
from anthropic.types.raw_content_block_delta import RawContentBlockDelta
from anthropic.types.raw_content_block_start_event import (
    ContentBlock as AnthropicContentBlock,
)
from anthropic.types.raw_message_delta_event import Delta
from pydantic import BaseModel

from aidial_sdk.translators.messages_to_chat_completions.errors import (
    INTERNAL_ERROR_MESSAGE,
    AnthropicErrorType,
    ErrorDetail,
    anthropic_error_type_from_stream,
)
from aidial_sdk.translators.messages_to_chat_completions.utils.log_config import (
    bedrock_logger as log,
)

_T = TypeVar("_T")
_T_co = TypeVar("_T_co", covariant=True)


class ClosableAsyncStream(Protocol[_T_co]):
    def __aiter__(self) -> AsyncIterator[_T_co]: ...

    async def close(self) -> None: ...


class _ErrorEvent(BaseModel):
    type: Literal["error"]
    error: ErrorDetail


AnthropicSSEEvent = (
    RawMessageStartEvent
    | RawContentBlockStartEvent
    | RawContentBlockDeltaEvent
    | RawContentBlockStopEvent
    | RawMessageDeltaEvent
    | RawMessageStopEvent
    | _ErrorEvent
)


def format_sse(event: AnthropicSSEEvent) -> bytes:
    data = event.model_dump_json(exclude_unset=True)
    return f"event: {event.type}\ndata: {data}\n\n".encode()


class AnthropicStreamState:
    def __init__(self, model: str) -> None:
        self.model = model
        self.message_id = str(uuid.uuid4())
        self.next_index = 0
        self.terminated = False

        self._open: tuple[Hashable, int] | None = None

    def is_open(self, key: Hashable) -> bool:
        return self._open is not None and self._open[0] == key

    def open_block(
        self, key: Hashable, content_block: AnthropicContentBlock
    ) -> Iterator[bytes]:
        yield from self.close_block()
        index = self.next_index
        self.next_index += 1
        self._open = (key, index)
        yield format_sse(
            RawContentBlockStartEvent(
                type="content_block_start",
                index=index,
                content_block=content_block,
            )
        )

    def delta(self, delta: RawContentBlockDelta) -> Iterator[bytes]:
        if self._open is None:
            log.warning(
                "Delta event has arrived before open event for a content block"
            )
            return
        yield format_sse(
            RawContentBlockDeltaEvent(
                type="content_block_delta", index=self._open[1], delta=delta
            )
        )

    def close_block(self) -> Iterator[bytes]:
        if self._open is None:
            return
        _, index = self._open
        self._open = None
        yield format_sse(
            RawContentBlockStopEvent(type="content_block_stop", index=index)
        )

    def message_start_events(self) -> Iterator[bytes]:
        yield format_sse(
            RawMessageStartEvent(
                type="message_start",
                message=Message(
                    id=self.message_id,
                    type="message",
                    role="assistant",
                    model=self.model,
                    content=[],
                    stop_reason=None,
                    stop_sequence=None,
                    usage=Usage(
                        input_tokens=0,
                        output_tokens=0,
                        cache_creation_input_tokens=0,
                        cache_read_input_tokens=0,
                    ),
                ),
            )
        )

    def final_events(
        self,
        stop_reason: StopReason,
        usage: Usage,
        stop_sequence: str | None = None,
    ) -> Iterator[bytes]:
        if self.terminated:
            return
        self.terminated = True
        yield from self.close_block()
        yield format_sse(
            RawMessageDeltaEvent(
                type="message_delta",
                delta=Delta(
                    stop_reason=stop_reason, stop_sequence=stop_sequence
                ),
                usage=MessageDeltaUsage(
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cache_creation_input_tokens=usage.cache_creation_input_tokens,
                    cache_read_input_tokens=usage.cache_read_input_tokens,
                    output_tokens_details=usage.output_tokens_details,
                ),
            )
        )
        yield format_sse(RawMessageStopEvent(type="message_stop"))

    def emit_error(
        self, error_type: AnthropicErrorType, message: str
    ) -> Iterator[bytes]:
        if self.terminated:
            return
        self.terminated = True
        yield format_sse(
            _ErrorEvent(
                type="error",
                error={"type": error_type.code, "message": message},
            )
        )


async def run_sse_stream(
    stream: ClosableAsyncStream[_T],
    state: AnthropicStreamState,
    on_item: Callable[[_T], Iterable[bytes]],
    on_finalize: Callable[[], Iterable[bytes]] | None = None,
    *,
    log_context: str,
) -> AsyncIterator[bytes]:
    try:
        async for item in stream:
            for chunk in on_item(item):
                yield chunk
        if on_finalize is not None:
            for chunk in on_finalize():
                yield chunk
    except openai.APIError as e:
        log.warning(f"DIAL Core reported an error in the {log_context} stream")
        for chunk in state.emit_error(
            anthropic_error_type_from_stream(e), e.message
        ):
            yield chunk
    except Exception:
        log.exception(f"Error while translating the {log_context} SSE stream")
        for chunk in state.emit_error(
            AnthropicErrorType.API, INTERNAL_ERROR_MESSAGE
        ):
            yield chunk
    finally:
        await stream.close()
