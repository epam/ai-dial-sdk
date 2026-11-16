import json
from collections.abc import Iterable, Iterator

from anthropic.types import (
    Message,
    StopReason,
    TextBlock,
    ToolUseBlock,
    Usage,
)
from anthropic.types.content_block import ContentBlock as AnthropicContentBlock
from anthropic.types.output_tokens_details import OutputTokensDetails
from anthropic.types.server_tool_usage import ServerToolUsage
from openai.types.responses import (
    Response,
    ResponseError,
    ResponseFunctionToolCall,
    ResponseFunctionWebSearch,
    ResponseOutputItem,
    ResponseOutputMessage,
    ResponseOutputRefusal,
    ResponseOutputText,
    ResponseReasoningItem,
    ResponseUsage,
)
from openai.types.responses.response import IncompleteDetails
from openai.types.responses.response_function_web_search import (
    ActionOpenPage,
    ActionSearch,
)
from openai.types.responses.response_output_text import AnnotationURLCitation

from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.translators._messages.translation_state import (
    TranslationState,
)
from aidial_sdk.translators._messages.web_search import (
    to_anthropic_web_search_blocks,
)
from aidial_sdk.translators.messages_to_responses.reasoning import (
    to_anthropic_thinking_block,
)
from aidial_sdk.utils.logging import logger as log

# The Responses API error codes, and the error types DIAL writes into a
# stream, that blame the request
_REQUEST_FAULTS = (
    "invalid_request_error",
    "context_length_exceeded",
    "invalid_prompt",
    "bio_policy",
    "invalid_image",
    "invalid_image_format",
    "invalid_base64_image",
    "invalid_image_url",
    "invalid_image_mode",
    "image_too_large",
    "image_too_small",
    "image_parse_error",
    "image_content_policy_violation",
    "image_file_too_large",
    "image_file_not_found",
    "unsupported_image_media_type",
    "empty_image_file",
    "failed_to_download_image",
)

_ERROR_STATUS_CODES: dict[str | None, int] = {
    "rate_limit_exceeded": 429,
    "vector_store_timeout": 504,
    **dict.fromkeys(_REQUEST_FAULTS, 400),
}


def to_anthropic_message(
    response: Response, model: str, translation_state: TranslationState
) -> Message:
    if response.status == "failed":
        raise from_response_error(response.error)

    content: list[AnthropicContentBlock] = []
    has_tool_call = is_refusal = False
    seen_urls: set[str] = set()
    for item in response.output:
        # Matched on `type` too: the openai SDK constructs an item of a type
        # it doesn't know as the first class of the union
        match item:
            case ResponseReasoningItem(type="reasoning"):
                if block := to_anthropic_thinking_block(item):
                    content.append(block)
            case ResponseOutputMessage(type="message"):
                content.extend(_to_anthropic_message_blocks(item, seen_urls))
                is_refusal = is_refusal or has_refusal(item)
            case ResponseFunctionToolCall(type="function_call"):
                has_tool_call = True
                content.append(
                    _to_anthropic_tool_use_block(item, translation_state)
                )
            case _:
                log.debug(f"Dropping Responses API output item: {item.type}")

    return Message(
        id=response.id,
        type="message",
        role="assistant",
        model=model,
        content=content or [TextBlock(type="text", text="")],
        stop_reason=to_anthropic_stop_reason(
            response.incomplete_details,
            has_tool_call=has_tool_call,
            is_refusal=is_refusal,
        ),
        usage=to_anthropic_usage(response.usage, response.output),
    )


def from_error_code(code: str | None, message: str) -> DIALException:
    return DIALException(
        message, status_code=_ERROR_STATUS_CODES.get(code, 500)
    )


def from_response_error(error: ResponseError | None) -> DIALException:
    if error is None:
        return DIALException("The Responses API response has failed")
    return from_error_code(error.code, error.message)


def has_refusal(item: ResponseOutputMessage) -> bool:
    return any(part.type == "refusal" for part in item.content)


def _to_anthropic_message_blocks(
    item: ResponseOutputMessage, seen_urls: set[str]
) -> Iterator[AnthropicContentBlock]:
    for part in item.content:
        match part:
            case ResponseOutputText(type="output_text"):
                yield TextBlock(type="text", text=part.text)
                yield from to_anthropic_web_search_blocks(
                    _new_citations(part, seen_urls)
                )
            case ResponseOutputRefusal(type="refusal"):
                yield TextBlock(type="text", text=part.refusal)


def to_anthropic_citation_blocks(
    item: ResponseOutputMessage, seen_urls: set[str]
) -> list[AnthropicContentBlock]:
    citations: list[tuple[str, str]] = []
    for part in item.content:
        match part:
            case ResponseOutputText(type="output_text"):
                citations.extend(_new_citations(part, seen_urls))
    return to_anthropic_web_search_blocks(citations)


def _new_citations(
    part: ResponseOutputText, seen_urls: set[str]
) -> list[tuple[str, str]]:
    citations: list[tuple[str, str]] = []
    for annotation in part.annotations:
        if (
            isinstance(annotation, AnnotationURLCitation)
            and annotation.type == "url_citation"
            and annotation.url not in seen_urls
        ):
            seen_urls.add(annotation.url)
            citations.append((annotation.url, annotation.title))
    return citations


def _to_anthropic_tool_use_block(
    item: ResponseFunctionToolCall, translation_state: TranslationState
) -> ToolUseBlock:
    return ToolUseBlock(
        type="tool_use",
        id=item.call_id,
        name=translation_state.to_client_tool_name(item.name),
        input=_parse_arguments(item.arguments),
    )


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
    incomplete_details: IncompleteDetails | None,
    *,
    has_tool_call: bool,
    is_refusal: bool,
) -> StopReason:
    reason = incomplete_details.reason if incomplete_details else None
    if reason == "max_output_tokens":
        return "max_tokens"
    if reason == "content_filter":
        return "refusal"
    if has_tool_call:
        return "tool_use"
    if is_refusal:
        return "refusal"
    return "end_turn"


def to_anthropic_usage(
    usage: ResponseUsage | None, output: Iterable[ResponseOutputItem]
) -> Usage:
    anthropic_usage = _to_anthropic_token_usage(usage)

    searches = fetches = 0
    for item in output:
        match item:
            case ResponseFunctionWebSearch(type="web_search_call"):
                match item.action:
                    case ActionSearch(type="search"):
                        searches += 1
                    case ActionOpenPage(type="open_page"):
                        fetches += 1
    if searches or fetches:
        anthropic_usage.server_tool_use = ServerToolUsage(
            web_search_requests=searches, web_fetch_requests=fetches
        )

    return anthropic_usage


def _to_anthropic_token_usage(usage: ResponseUsage | None) -> Usage:
    if usage is None:
        return Usage(input_tokens=0, output_tokens=0)

    input_tokens = usage.input_tokens or 0
    input_details = usage.input_tokens_details
    # Anthropic's input_tokens excludes cache reads and writes, which
    # input_tokens includes: cap the breakdown so the counters add up.
    cache_read = min(
        (input_details.cached_tokens if input_details else 0) or 0,
        input_tokens,
    )
    cache_write = min(
        (input_details.cache_write_tokens if input_details else 0) or 0,
        input_tokens - cache_read,
    )

    output_details = usage.output_tokens_details
    thinking = (output_details.reasoning_tokens if output_details else 0) or 0

    return Usage(
        input_tokens=input_tokens - cache_read - cache_write,
        output_tokens=usage.output_tokens or 0,
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_write,
        output_tokens_details=OutputTokensDetails(thinking_tokens=thinking),
    )
