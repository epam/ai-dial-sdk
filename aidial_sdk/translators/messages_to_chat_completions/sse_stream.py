import json
import uuid
from collections.abc import (
    AsyncGenerator,
    AsyncIterator,
    Callable,
    Hashable,
    Iterable,
    Iterator,
)
from typing import TypeVar

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

from aidial_sdk._errors import to_dial_exception
from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.utils.logging import logger as log

_T = TypeVar("_T")


AnthropicSSEEvent = (
    RawMessageStartEvent
    | RawContentBlockStartEvent
    | RawContentBlockDeltaEvent
    | RawContentBlockStopEvent
    | RawMessageDeltaEvent
    | RawMessageStopEvent
)


def format_sse(event: AnthropicSSEEvent | dict) -> bytes:
    if isinstance(event, dict):
        name, data = event["type"], json.dumps(event, separators=(",", ":"))
    else:
        name, data = event.type, event.model_dump_json(exclude_unset=True)
    return f"event: {name}\ndata: {data}\n\n".encode()


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

    def emit_error(self, error: DIALException) -> Iterator[bytes]:
        if self.terminated:
            return
        self.terminated = True
        yield format_sse(error.json_error("anthropic"))


async def run_sse_stream(
    stream: AsyncGenerator[_T, None],
    state: AnthropicStreamState,
    on_item: Callable[[_T], Iterable[bytes]],
    on_finalize: Callable[[], Iterable[bytes]] | None = None,
) -> AsyncIterator[bytes]:
    try:
        async for item in stream:
            for chunk in on_item(item):
                yield chunk
        if on_finalize is not None:
            for chunk in on_finalize():
                yield chunk
    except Exception as e:
        for chunk in state.emit_error(to_dial_exception(e)):
            yield chunk
    finally:
        await stream.aclose()
