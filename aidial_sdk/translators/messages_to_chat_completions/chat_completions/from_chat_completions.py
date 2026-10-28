import json
import uuid
from typing import assert_never

from anthropic.types import (
    Message,
    ServerToolUseBlock,
    StopReason,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    Usage,
    WebSearchToolResultBlock,
)
from anthropic.types.content_block import ContentBlock as AnthropicContentBlock
from anthropic.types.output_tokens_details import OutputTokensDetails
from anthropic.types.web_search_result_block import WebSearchResultBlock
from openai.types.chat import ChatCompletion
from openai.types.chat.chat_completion_message import (
    Annotation,
    ChatCompletionMessage,
)
from openai.types.chat.chat_completion_message_tool_call import (
    ChatCompletionMessageToolCallUnion,
)
from openai.types.completion_usage import CompletionUsage, PromptTokensDetails

from aidial_sdk.translators.messages_to_chat_completions.chat_completions.dial_extensions import (
    CustomContent,
    get_claude_thinking_block,
    get_dial_reasoning_content,
    parse_extras,
)
from aidial_sdk.translators.messages_to_chat_completions.translation_state import (
    TranslationState,
)
from aidial_sdk.utils.logging import logger as log


def to_anthropic_response(
    response: ChatCompletion,
    requested_model: str,
    translation_state: TranslationState,
) -> Message:
    if len(response.choices) > 1:
        log.warning(
            f"Ignoring {len(response.choices) - 1} choices after the first one"
        )
    choice = response.choices[0] if response.choices else None
    message = choice.message if choice else None
    tool_blocks = _to_anthropic_tool_use_blocks(
        message.tool_calls if message else None, translation_state
    )

    return Message(
        id=response.id,
        type="message",
        role="assistant",
        model=requested_model,
        content=_to_anthropic_content_blocks(message, tool_blocks),
        stop_reason=to_anthropic_stop_reason(
            choice.finish_reason if choice else None,
            bool(tool_blocks),
            bool(message and message.refusal),
        ),
        usage=to_anthropic_usage(response.usage),
    )


def _to_anthropic_content_blocks(
    message: ChatCompletionMessage | None,
    tool_blocks: list[ToolUseBlock],
) -> list[AnthropicContentBlock]:
    if message is None:
        return [_text_block("")]

    content: list[AnthropicContentBlock] = []

    extras = parse_extras(message.model_extra)
    if thinking := to_anthropic_thinking_block(extras.custom_content):
        content.append(thinking)

    content.extend(
        to_anthropic_web_search_blocks(_citations(message.annotations))
    )

    if message.content:
        content.append(_text_block(message.content))

    if message.refusal:
        content.append(_text_block(message.refusal))

    content.extend(tool_blocks)

    return content or [_text_block("")]


def _text_block(text: str) -> TextBlock:
    return TextBlock(type="text", text=text)


def to_anthropic_thinking_block(
    custom_content: CustomContent | None,
) -> ThinkingBlock | None:
    if block := get_claude_thinking_block(custom_content):
        return ThinkingBlock(
            type="thinking",
            thinking=block.thinking or "",
            signature=block.signature or "",
        )
    if text := get_dial_reasoning_content(custom_content):
        return ThinkingBlock(type="thinking", thinking=text, signature="")
    return None


def _citations(annotations: list[Annotation] | None) -> list[tuple[str, str]]:
    return [
        (annotation.url_citation.url, annotation.url_citation.title)
        for annotation in annotations or []
    ]


def to_anthropic_web_search_blocks(
    citations: list[tuple[str, str]],
) -> list[AnthropicContentBlock]:
    if not citations:
        return []
    tool_use_id = f"srvtoolu_{uuid.uuid4().hex}"
    return [
        ServerToolUseBlock(
            type="server_tool_use",
            id=tool_use_id,
            name="web_search",
            input={"query": ""},
        ),
        WebSearchToolResultBlock(
            type="web_search_tool_result",
            tool_use_id=tool_use_id,
            content=[
                WebSearchResultBlock(
                    type="web_search_result",
                    url=url,
                    title=title,
                    encrypted_content="",
                )
                for url, title in citations
            ],
        ),
    ]


def _to_anthropic_tool_use_blocks(
    tool_calls: list[ChatCompletionMessageToolCallUnion] | None,
    translation_state: TranslationState,
) -> list[ToolUseBlock]:
    blocks: list[ToolUseBlock] = []
    for call in tool_calls or []:
        match call.type:
            case "custom":
                log.warning(f"Skipping unsupported tool call type: {call.type}")
                continue
            case "function":
                pass
            case unexpected:
                assert_never(unexpected)
        blocks.append(
            ToolUseBlock(
                type="tool_use",
                id=call.id,
                name=translation_state.to_client_tool_name(call.function.name),
                input=_parse_arguments(call.function.arguments),
            )
        )
    return blocks


def _parse_arguments(arguments: str) -> dict[str, object]:
    try:
        parsed = json.loads(arguments) if arguments else {}
    except json.JSONDecodeError:
        parsed = None
    if not isinstance(parsed, dict):
        log.warning("Failed to parse function_call arguments as a JSON object")
        return {}
    return parsed


def to_anthropic_stop_reason(
    finish_reason: str | None,
    has_tool_call: bool,
    is_refusal: bool,
) -> StopReason:
    if finish_reason == "length":
        return "max_tokens"
    if finish_reason == "content_filter":
        return "refusal"
    if has_tool_call:
        return "tool_use"
    if is_refusal:
        return "refusal"
    return "end_turn"


def to_anthropic_usage(usage: CompletionUsage | None) -> Usage:
    if usage is None:
        return Usage(input_tokens=0, output_tokens=0)

    prompt_tokens = usage.prompt_tokens or 0
    prompt_details = usage.prompt_tokens_details
    # Anthropic's input_tokens excludes cache reads and writes, which
    # prompt_tokens includes: cap the breakdown so the counters add up.
    cache_read = min(
        (prompt_details.cached_tokens if prompt_details else 0) or 0,
        prompt_tokens,
    )
    cache_write = min(
        _cache_write_tokens(prompt_details), prompt_tokens - cache_read
    )

    completion_details = usage.completion_tokens_details
    thinking = (
        completion_details.reasoning_tokens if completion_details else 0
    ) or 0

    return Usage(
        input_tokens=prompt_tokens - cache_read - cache_write,
        output_tokens=usage.completion_tokens or 0,
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_write,
        output_tokens_details=OutputTokensDetails(thinking_tokens=thinking),
    )


def _cache_write_tokens(details: PromptTokensDetails | None) -> int:
    if details is None:
        return 0
    return details.cache_write_tokens or 0
