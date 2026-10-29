from collections.abc import AsyncIterator, Iterator

from anthropic.types import (
    RawContentBlockDeltaEvent,
    RawContentBlockStartEvent,
    RawContentBlockStopEvent,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)
from anthropic.types.input_json_delta import InputJSONDelta
from anthropic.types.signature_delta import SignatureDelta
from anthropic.types.text_delta import TextDelta
from anthropic.types.thinking_delta import ThinkingDelta
from openai.types.chat import ChatCompletionChunk
from openai.types.chat.chat_completion_chunk import Choice, ChoiceDeltaToolCall
from openai.types.completion_usage import CompletionUsage

from aidial_sdk.translators.messages_to_chat_completions.chat_completions.dial_extensions import (
    CustomContent,
    is_reasoning_stage,
    parse_extras,
)
from aidial_sdk.translators.messages_to_chat_completions.chat_completions.from_chat_completions import (
    to_anthropic_stop_reason,
    to_anthropic_usage,
    to_anthropic_web_search_blocks,
)
from aidial_sdk.translators.messages_to_chat_completions.sse_stream import (
    AnthropicStreamState,
    ClosableAsyncStream,
    format_sse,
    run_sse_stream,
)
from aidial_sdk.translators.messages_to_chat_completions.translation_state import (
    TranslationState,
)
from aidial_sdk.utils.logging import logger as log
from aidial_sdk.utils.merge_chunks import merge

_TEXT_KEY = "text"
_THINKING_KEY = "thinking"
_CITATION_KEY = "citation"


class ChatCompletionsToAnthropicStream(AnthropicStreamState):
    def __init__(
        self,
        requested_model: str,
        translation_state: TranslationState,
    ) -> None:
        super().__init__(requested_model)
        self.started = False
        self.finish_reason: str | None = None
        self.usage: CompletionUsage | None = None
        self.is_refusal = False
        self.has_tool_call = False
        self._translation_state = translation_state
        self._reasoning_stages: set[int | None] = set()
        self._seen_citations: set[str] = set()
        self._signed = False
        self._tools: dict[int, int] = {}

    def handle(self, chunk: ChatCompletionChunk) -> Iterator[bytes]:
        if self.terminated:
            return

        if not self.started:
            self.message_id = chunk.id
            yield from self._start()

        if chunk.choices:
            yield from self._on_choice(chunk.choices[0])

        if chunk.usage is not None:
            self.usage = _merge_usage(self.usage, chunk.usage)

    def _start(self) -> Iterator[bytes]:
        self.started = True
        yield from self.message_start_events()

    def _on_choice(self, choice: Choice) -> Iterator[bytes]:
        delta = choice.delta
        extras = parse_extras(delta.model_extra)

        if choice.finish_reason:
            self.finish_reason = choice.finish_reason
        yield from self._on_custom_content(extras.custom_content)

        if text := delta.content:
            yield from self._emit_text(text)
        if refusal := delta.refusal:
            self.is_refusal = True
            yield from self._emit_text(refusal)

        citations: list[tuple[str, str]] = []
        for annotation in extras.annotations or []:
            citation = annotation.url_citation
            if citation.url not in self._seen_citations:
                self._seen_citations.add(citation.url)
                citations.append((citation.url, citation.title))
        if citations:
            yield from self._close_tools()
            for block in to_anthropic_web_search_blocks(citations):
                yield from self.open_block(_CITATION_KEY, block)
                yield from self.close_block()
        for call in delta.tool_calls or []:
            yield from self._on_tool_call_delta(call)

    def _on_custom_content(
        self, custom_content: CustomContent | None
    ) -> Iterator[bytes]:
        if custom_content is None:
            return

        for stage in custom_content.stages or []:
            if is_reasoning_stage(stage.name):
                self._reasoning_stages.add(stage.index)
            if stage.index in self._reasoning_stages and stage.content:
                yield from self._thinking_delta(stage.content)

        if self._signed or custom_content.state is None:
            return
        for block in custom_content.state.claude_message_content or []:
            if block.type == "thinking" and block.signature:
                self._signed = True
                yield from self._signature_delta(block.signature)
                break

    def _thinking_delta(self, text: str) -> Iterator[bytes]:
        yield from self._close_tools()
        if not self.is_open(_THINKING_KEY):
            yield from self.open_block(
                _THINKING_KEY,
                ThinkingBlock(type="thinking", thinking="", signature=""),
            )
        yield from self.delta(
            ThinkingDelta(type="thinking_delta", thinking=text)
        )

    def _signature_delta(self, signature: str) -> Iterator[bytes]:
        if not self.is_open(_THINKING_KEY):
            log.warning("Thinking signature arrived after the block closed")
            return

        yield from self.delta(
            SignatureDelta(type="signature_delta", signature=signature)
        )
        yield from self.close_block()

    def _emit_text(self, text: str) -> Iterator[bytes]:
        yield from self._close_tools()
        if not self.is_open(_TEXT_KEY):
            yield from self.open_block(
                _TEXT_KEY, TextBlock(type="text", text="")
            )
        yield from self.delta(TextDelta(type="text_delta", text=text))

    def _on_tool_call_delta(self, call: ChoiceDeltaToolCall) -> Iterator[bytes]:
        if call.type not in (None, "function"):
            return
        yield from self.close_block()
        function = call.function
        if call.index not in self._tools:
            self.has_tool_call = True
            self._tools[call.index] = self.next_index
            self.next_index += 1
            yield format_sse(
                RawContentBlockStartEvent(
                    type="content_block_start",
                    index=self._tools[call.index],
                    content_block=ToolUseBlock(
                        type="tool_use",
                        id=call.id or "",
                        name=self._translation_state.to_client_tool_name(
                            (function.name if function else None) or ""
                        ),
                        input={},
                    ),
                )
            )
        if function and function.arguments:
            yield format_sse(
                RawContentBlockDeltaEvent(
                    type="content_block_delta",
                    index=self._tools[call.index],
                    delta=InputJSONDelta(
                        type="input_json_delta",
                        partial_json=function.arguments,
                    ),
                )
            )

    def _close_tools(self) -> Iterator[bytes]:
        for index in self._tools.values():
            yield format_sse(
                RawContentBlockStopEvent(type="content_block_stop", index=index)
            )
        self._tools.clear()

    def finalize(self) -> Iterator[bytes]:
        if self.terminated:
            return

        if not self.started:
            yield from self._start()
        yield from self._close_tools()
        if self.next_index == 0:
            yield from self.open_block(
                _TEXT_KEY, TextBlock(type="text", text="")
            )

        yield from self.final_events(
            to_anthropic_stop_reason(
                self.finish_reason, self.has_tool_call, self.is_refusal
            ),
            to_anthropic_usage(self.usage),
        )


def _merge_usage(
    current: CompletionUsage | None, update: CompletionUsage
) -> CompletionUsage:
    if current is None:
        return update
    return CompletionUsage.model_validate(
        merge(current.model_dump(), update.model_dump())
    )


async def translate_stream(
    stream: ClosableAsyncStream[ChatCompletionChunk],
    requested_model: str,
    translation_state: TranslationState,
) -> AsyncIterator[bytes]:
    state = ChatCompletionsToAnthropicStream(requested_model, translation_state)

    async for chunk in run_sse_stream(
        stream,
        state,
        state.handle,
        on_finalize=state.finalize,
        log_context="Chat Completions",
    ):
        yield chunk
