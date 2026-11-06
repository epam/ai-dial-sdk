from collections.abc import AsyncGenerator, AsyncIterator, Hashable, Iterator
from typing import Any

from anthropic.types import TextBlock, ThinkingBlock, ToolUseBlock
from anthropic.types.input_json_delta import InputJSONDelta
from anthropic.types.raw_content_block_start_event import (
    ContentBlock as AnthropicContentBlock,
)
from anthropic.types.signature_delta import SignatureDelta
from anthropic.types.text_delta import TextDelta
from anthropic.types.thinking_delta import ThinkingDelta
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

ResponsesEvent = dict[str, Any]

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

        # The events are dispatched on `type` before they are constructed:
        # the openai SDK constructs an event of a type it doesn't know as the
        # first class of the union
        match event.get("type"):
            case "response.created":
                created = ResponseCreatedEvent.model_construct(**event)
                self.message_id = created.response.id
                yield from self._start()
            case "response.output_item.added":
                yield from self._on_item_added(
                    ResponseOutputItemAddedEvent.model_construct(**event)
                )
            case "response.output_text.delta":
                text = ResponseTextDeltaEvent.model_construct(**event)
                yield from self._text_delta(
                    ("text", text.output_index, text.content_index), text.delta
                )
            case "response.refusal.delta":
                refusal = ResponseRefusalDeltaEvent.model_construct(**event)
                yield from self._text_delta(
                    ("text", refusal.output_index, refusal.content_index),
                    refusal.delta,
                )
            case "response.function_call_arguments.delta":
                yield from self._on_arguments_delta(
                    ResponseFunctionCallArgumentsDeltaEvent.model_construct(
                        **event
                    )
                )
            case "response.reasoning_summary_text.delta":
                summary = (
                    ResponseReasoningSummaryTextDeltaEvent.model_construct(
                        **event
                    )
                )
                yield from self._thinking_delta(
                    summary.output_index,
                    ("summary", summary.summary_index),
                    summary.delta,
                )
            case "response.reasoning_text.delta":
                reasoning = ResponseReasoningTextDeltaEvent.model_construct(
                    **event
                )
                yield from self._thinking_delta(
                    reasoning.output_index,
                    ("content", reasoning.content_index),
                    reasoning.delta,
                )
            case "response.output_item.done":
                yield from self._on_item_done(
                    ResponseOutputItemDoneEvent.model_construct(**event)
                )
            case "response.completed":
                completed = ResponseCompletedEvent.model_construct(**event)
                yield from self._finish(completed)
            case "response.incomplete":
                incomplete = ResponseIncompleteEvent.model_construct(**event)
                yield from self._finish(incomplete)
            case "response.failed":
                failed = ResponseFailedEvent.model_construct(**event)
                yield from self.emit_error(
                    from_response_error(failed.response.error)
                )
            case "error":
                error = ResponseErrorEvent.model_construct(**event)
                yield from self.emit_error(
                    from_error_code(error.code, error.message)
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
        key: _ItemKey
        match event.item:
            case ResponseFunctionToolCall(type="function_call"):
                key = ("function", event.output_index)
                if (
                    self.is_open(key)
                    and event.output_index not in self._streamed_arguments
                    and event.item.arguments
                ):
                    # The arguments an upstream sent without the deltas
                    yield from self.delta(
                        InputJSONDelta(
                            type="input_json_delta",
                            partial_json=event.item.arguments,
                        )
                    )
                if self.is_open(key):
                    yield from self.close_block()
            case ResponseReasoningItem(type="reasoning"):
                key = ("reasoning", event.output_index)
                yield from self._on_reasoning_done(key, event.item)
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
