from collections.abc import AsyncGenerator, AsyncIterator, Hashable, Iterator
from typing import Any, cast

from anthropic.types import TextBlock, ThinkingBlock, ToolUseBlock
from anthropic.types.input_json_delta import InputJSONDelta
from anthropic.types.raw_content_block_start_event import (
    ContentBlock as AnthropicContentBlock,
)
from anthropic.types.signature_delta import SignatureDelta
from anthropic.types.text_delta import TextDelta
from anthropic.types.thinking_delta import ThinkingDelta
from openai._models import construct_type_unchecked
from openai.types.responses import (
    ResponseCompletedEvent,
    ResponseCreatedEvent,
    ResponseErrorEvent,
    ResponseFailedEvent,
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseFunctionToolCall,
    ResponseIncompleteEvent,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseOutputMessage,
    ResponseReasoningItem,
    ResponseReasoningSummaryTextDeltaEvent,
    ResponseReasoningTextDeltaEvent,
    ResponseRefusalDeltaEvent,
    ResponseStreamEvent,
    ResponseTextDeltaEvent,
)

from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.translators._messages.sse_stream import (
    AnthropicStreamState,
    Heartbeat,
    format_sse,
    run_sse_stream,
)
from aidial_sdk.translators._messages.translation_state import (
    TranslationState,
)
from aidial_sdk.translators.messages_to_responses.from_responses import (
    from_error_code,
    from_response_error,
    has_refusal,
    to_anthropic_citation_blocks,
    to_anthropic_stop_reason,
    to_anthropic_usage,
)
from aidial_sdk.translators.messages_to_responses.reasoning import (
    to_anthropic_thinking_block,
    to_signature,
)
from aidial_sdk.utils.logging import logger as log

ResponsesEvent = ResponseStreamEvent


def parse_event(data: object) -> ResponsesEvent:
    """The event of the class of its `type`. An event of an unknown type gets
    the class of the first type, which `_ResponsesToAnthropicStream.handle`
    ignores."""
    return construct_type_unchecked(
        value=data, type_=cast(Any, ResponseStreamEvent)
    )


# The keys of the open block: a text is a content part of an output item,
# a tool call and a reasoning are output items
_TextKey = tuple[str, int, int]
_ItemKey = tuple[str, int]


class _ResponsesToAnthropicStream(AnthropicStreamState):
    def __init__(self, model: str, translation_state: TranslationState) -> None:
        super().__init__(model)
        self.started = False
        self._translation_state = translation_state
        self._has_tool_call = False
        self._is_refusal = False
        self._streamed_arguments: set[int] = set()
        self._reasoning_part: tuple[str, int] | None = None
        self._seen_urls: set[str] = set()

    def handle(self, event: ResponsesEvent | Heartbeat) -> Iterator[bytes]:
        if self.terminated:
            return

        if isinstance(event, Heartbeat):
            yield format_sse({"type": "ping"})
            return

        match event:
            case ResponseCreatedEvent():
                self.message_id = event.response.id
                yield from self._start()
            case ResponseOutputItemAddedEvent():
                yield from self._on_item_added(event)
            case ResponseTextDeltaEvent() | ResponseRefusalDeltaEvent():
                yield from self._text_delta(
                    ("text", event.output_index, event.content_index),
                    event.delta,
                )
            case ResponseFunctionCallArgumentsDeltaEvent():
                yield from self._on_arguments_delta(event)
            case ResponseReasoningSummaryTextDeltaEvent():
                yield from self._thinking_delta(
                    event.output_index,
                    ("summary", event.summary_index),
                    event.delta,
                )
            case ResponseReasoningTextDeltaEvent():
                yield from self._thinking_delta(
                    event.output_index,
                    ("content", event.content_index),
                    event.delta,
                )
            case ResponseOutputItemDoneEvent():
                yield from self._on_item_done(event)
            case ResponseCompletedEvent() | ResponseIncompleteEvent():
                yield from self._finish(event)
            case ResponseFailedEvent():
                yield from self.emit_error(
                    from_response_error(event.response.error)
                )
            case ResponseErrorEvent():
                yield from self.emit_error(
                    from_error_code(event.code, event.message)
                )
            case _:
                pass

    def _start(self) -> Iterator[bytes]:
        if not self.started:
            self.started = True
            yield from self.message_start_events()

    def open_block(
        self, key: Hashable, content_block: AnthropicContentBlock
    ) -> Iterator[bytes]:
        yield from self._start()
        yield from super().open_block(key, content_block)

    def _text_delta(self, key: _TextKey, text: str) -> Iterator[bytes]:
        if not self.is_open(key):
            yield from self.open_block(key, TextBlock(type="text", text=""))
        yield from self.delta(TextDelta(type="text_delta", text=text))

    def _thinking_delta(
        self, output_index: int, part: tuple[str, int], text: str
    ) -> Iterator[bytes]:
        if not text:
            return
        key: _ItemKey = ("reasoning", output_index)
        if not self.is_open(key):
            yield from self.open_block(
                key, ThinkingBlock(type="thinking", thinking="", signature="")
            )
        elif part != self._reasoning_part:
            # Separates the summary parts the way a block response joins them
            text = f"\n\n{text}"
        self._reasoning_part = part
        yield from self.delta(
            ThinkingDelta(type="thinking_delta", thinking=text)
        )

    def _on_item_added(
        self, event: ResponseOutputItemAddedEvent
    ) -> Iterator[bytes]:
        match event.item:
            case ResponseFunctionToolCall(type="function_call"):
                self._has_tool_call = True
                yield from self.open_block(
                    ("function", event.output_index),
                    ToolUseBlock(
                        type="tool_use",
                        id=event.item.call_id,
                        name=self._translation_state.to_client_tool_name(
                            event.item.name
                        ),
                        input={},
                    ),
                )

    def _on_arguments_delta(
        self, event: ResponseFunctionCallArgumentsDeltaEvent
    ) -> Iterator[bytes]:
        if (
            not self.is_open(("function", event.output_index))
            or not event.delta
        ):
            return
        self._streamed_arguments.add(event.output_index)
        yield from self.delta(
            InputJSONDelta(type="input_json_delta", partial_json=event.delta)
        )

    def _on_item_done(
        self, event: ResponseOutputItemDoneEvent
    ) -> Iterator[bytes]:
        match event.item:
            case ResponseFunctionToolCall(type="function_call"):
                if not self.is_open(("function", event.output_index)):
                    return
                if (
                    event.output_index not in self._streamed_arguments
                    and event.item.arguments
                ):
                    # The arguments an upstream sent without the deltas
                    yield from self.delta(
                        InputJSONDelta(
                            type="input_json_delta",
                            partial_json=event.item.arguments,
                        )
                    )
                yield from self.close_block()
            case ResponseReasoningItem(type="reasoning"):
                yield from self._on_reasoning_done(
                    ("reasoning", event.output_index), event.item
                )
            case ResponseOutputMessage(type="message"):
                for block in to_anthropic_citation_blocks(
                    event.item, self._seen_urls
                ):
                    yield from self.open_block("citation", block)
                    yield from self.close_block()
                self._is_refusal = self._is_refusal or has_refusal(event.item)
            case _:
                pass

    def _on_reasoning_done(
        self, key: _ItemKey, item: ResponseReasoningItem
    ) -> Iterator[bytes]:
        if self.is_open(key):
            # The encrypted reasoning arrives once its text has been streamed
            if signature := to_signature(item):
                yield from self.delta(
                    SignatureDelta(type="signature_delta", signature=signature)
                )
            yield from self.close_block()
        elif block := to_anthropic_thinking_block(item):
            yield from self.open_block(key, block)
            yield from self.close_block()

    def _finish(
        self, event: ResponseCompletedEvent | ResponseIncompleteEvent
    ) -> Iterator[bytes]:
        yield from self._start()
        if self.next_index == 0:
            yield from self.open_block("text", TextBlock(type="text", text=""))
        response = event.response
        yield from self.final_events(
            to_anthropic_stop_reason(
                response.incomplete_details,
                has_tool_call=self._has_tool_call,
                is_refusal=self._is_refusal,
            ),
            to_anthropic_usage(response.usage, response.output),
        )

    def finalize(self) -> Iterator[bytes]:
        if not self.terminated:
            log.warning("The Responses API stream ended without a final event")
            yield from self.emit_error(
                DIALException(
                    "The Responses API stream ended before the response completed",
                    status_code=502,
                )
            )


async def translate_stream(
    stream: AsyncGenerator[ResponsesEvent | Heartbeat, None],
    model: str,
    translation_state: TranslationState,
) -> AsyncIterator[bytes]:
    state = _ResponsesToAnthropicStream(model, translation_state)
    async for chunk in run_sse_stream(
        stream, state, state.handle, on_finalize=state.finalize
    ):
        yield chunk
