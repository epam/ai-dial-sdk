import json
from collections.abc import Iterable
from typing import Literal, Required, TypedDict, cast

from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaContentBlockSourceContentParam,
    BetaImageBlockParam,
    BetaRequestDocumentBlockParam,
    BetaSearchResultBlockParam,
    BetaTextBlockParam,
    BetaToolChoiceParam,
    BetaToolParam,
    BetaToolResultBlockParam,
    BetaToolUnionParam,
    BetaWebSearchTool20250305Param,
)
from anthropic.types.beta.beta_tool_result_block_param import (
    Content as ToolResultContent,
)
from anthropic.types.beta.message_create_params import MessageCreateParams
from openai.types.responses import (
    EasyInputMessageParam,
    FunctionToolParam,
    ResponseFunctionToolCallParam,
    ResponseIncludable,
    ResponseInputFileParam,
    ResponseInputImageParam,
    ResponseInputTextParam,
    ResponseReasoningItemParam,
    ResponseTextConfigParam,
    ToolParam,
    WebSearchToolParam,
)
from openai.types.responses.response_create_params import ToolChoice
from openai.types.responses.response_input_message_content_list_param import (
    ResponseInputContentParam,
)
from openai.types.shared_params import Reasoning

from aidial_sdk.exceptions import InvalidRequestError
from aidial_sdk.translators.messages_to_chat_completions.chat_completions.reasoning import (
    resolve_effort,
)
from aidial_sdk.translators.messages_to_chat_completions.chat_completions.system_turns import (
    visible_messages,
)
from aidial_sdk.translators.messages_to_chat_completions.translation_state import (
    TranslationState,
)
from aidial_sdk.translators.messages_to_responses.reasoning import (
    to_reasoning_item,
)
from aidial_sdk.utils.logging import logger as log

# The Responses API rejects a smaller output budget, e.g. the one-token
# budget of the Claude Code probes
_MIN_OUTPUT_TOKENS = 16
_MAX_USER_LENGTH = 64

_SERVICE_TIERS: dict[str, Literal["auto", "default"]] = {
    "auto": "auto",
    "standard_only": "default",
}

_FILES_API_UNSUPPORTED = (
    "Files uploaded via Anthropic Files API aren't supported."
)


class FunctionCallOutputParam(TypedDict):
    # The openai SDK types the content parts of a function call output apart
    # from the ones of a message, while the API takes the same parts in both
    type: Literal["function_call_output"]
    call_id: str
    output: str | list[ResponseInputContentParam]


InputItem = (
    EasyInputMessageParam
    | ResponseFunctionToolCallParam
    | FunctionCallOutputParam
    | ResponseReasoningItemParam
)


class ResponsesRequest(TypedDict, total=False):
    # Not ResponseCreateParams: an Anthropic tool with no Responses API
    # counterpart is forwarded as sent, for the deployment to reject
    model: str
    input: Required[list[InputItem]]
    instructions: str
    tools: list[ToolParam | BetaToolUnionParam]
    tool_choice: ToolChoice
    parallel_tool_calls: bool
    reasoning: Reasoning
    text: ResponseTextConfigParam
    max_output_tokens: int
    max_tool_calls: int
    temperature: float
    top_p: float
    service_tier: Literal["auto", "default"]
    user: str
    store: Required[bool]
    include: Required[list[ResponseIncludable]]
    stream: Required[bool]


def to_responses_request(
    req: MessageCreateParams, translation_state: TranslationState
) -> ResponsesRequest:
    _warn_dropped(req)

    request: ResponsesRequest = {
        "input": _to_input_items(req, translation_state),
        # The Messages API keeps no state between the requests
        "store": False,
        # Replays the reasoning of the previous turns without stored state
        "include": ["reasoning.encrypted_content"],
        "stream": bool(req.get("stream")),
    }

    if (model := req.get("model")) is not None:
        request["model"] = model
    if instructions := _to_instructions(req.get("system")):
        request["instructions"] = instructions

    tools = req.get("tools") or []
    if converted_tools := [
        _to_responses_tool(tool, translation_state) for tool in tools
    ]:
        request["tools"] = converted_tools
    if (max_tool_calls := _to_max_tool_calls(tools)) is not None:
        request["max_tool_calls"] = max_tool_calls

    if (tool_choice := req.get("tool_choice")) is not None:
        if (
            converted_choice := _to_tool_choice(
                tool_choice, tools, translation_state
            )
        ) is not None:
            request["tool_choice"] = converted_choice
        if "disable_parallel_tool_use" in tool_choice:
            request["parallel_tool_calls"] = not tool_choice[
                "disable_parallel_tool_use"
            ]

    if reasoning := _to_reasoning(req):
        request["reasoning"] = reasoning
    if (text := _to_text_config(req)) is not None:
        request["text"] = text

    if (max_tokens := req.get("max_tokens")) is not None:
        request["max_output_tokens"] = (
            _MIN_OUTPUT_TOKENS
            if 0 < max_tokens < _MIN_OUTPUT_TOKENS
            else max_tokens
        )
    if (temperature := req.get("temperature")) is not None:
        request["temperature"] = temperature
    if (top_p := req.get("top_p")) is not None:
        request["top_p"] = top_p
    if (tier := _SERVICE_TIERS.get(req.get("service_tier") or "")) is not None:
        request["service_tier"] = tier
    if user := _to_user(req):
        request["user"] = user

    return request


def _warn_dropped(req: MessageCreateParams) -> None:
    unsupported = (
        "top_k",
        "stop_sequences",
        "compaction",
        "mcp_servers",
        "container",
        "inference_geo",
        "context_management",
    )
    if params := [key for key in unsupported if key in req]:
        log.warning(
            "Ignoring Anthropic Messages API parameters that have no "
            f"Responses API equivalent: {', '.join(params)}."
        )


def _to_user(req: MessageCreateParams) -> str | None:
    user_id = (req.get("metadata") or {}).get("user_id")
    if user_id and len(user_id) > _MAX_USER_LENGTH:
        # Truncated, the id would name another user
        log.debug(
            f"Dropping metadata.user_id: it's longer than the "
            f"{_MAX_USER_LENGTH} characters the Responses API accepts"
        )
        return None
    return user_id


def _to_text_config(req: MessageCreateParams) -> ResponseTextConfigParam | None:
    output_format = (req.get("output_config") or {}).get("format")
    if output_format is None:
        return None
    if output_format.get("type") != "json_schema":
        log.warning(
            "Dropping unsupported output_config.format type: "
            f"{output_format.get('type')}"
        )
        return None
    if not (schema := output_format.get("schema")):
        log.warning("Dropping output_config.format: missing 'schema'")
        return None
    return {
        "format": {
            "type": "json_schema",
            "name": "response",
            "schema": schema,
            "strict": True,
        }
    }


def _to_reasoning(req: MessageCreateParams) -> Reasoning:
    reasoning: Reasoning = {}
    if (effort := resolve_effort(req)) is not None:
        reasoning["effort"] = effort

    # Unlike Anthropic, the Responses API returns no reasoning text unless
    # asked for a summary
    thinking = req.get("thinking")
    if (
        thinking is not None
        and effort != "none"
        and thinking.get("display") != "omitted"
    ):
        reasoning["summary"] = "auto"

    return reasoning


def _to_instructions(
    system: str | Iterable[BetaTextBlockParam] | None,
) -> str:
    return "\n\n".join(part["text"] for part in _system_parts(system))


def _to_input_items(
    req: MessageCreateParams, translation_state: TranslationState
) -> list[InputItem]:
    items: list[InputItem] = []
    for message in visible_messages(req["messages"]):
        match message["role"]:
            case "user":
                items.extend(_from_user_turn(message["content"]))
            case "assistant":
                items.extend(
                    _from_assistant_turn(message["content"], translation_state)
                )
            case "system":
                items.extend(_from_system_turn(message["content"]))
            case unsupported:
                raise InvalidRequestError(
                    f"Unsupported message role: {unsupported}"
                )
    return items


def _message(
    role: Literal["user", "assistant", "system"],
    content: str | list[ResponseInputContentParam],
) -> EasyInputMessageParam:
    return {"type": "message", "role": role, "content": content}


def _text_part(text: str) -> ResponseInputTextParam:
    return {"type": "input_text", "text": text}


def _from_system_turn(
    content: str | Iterable[BetaContentBlockParam] | None,
) -> list[InputItem]:
    parts: list[ResponseInputContentParam] = [*_system_parts(content)]
    return [_message("system", parts)] if parts else []


def _system_parts(
    content: str | Iterable[BetaContentBlockParam] | None,
) -> list[ResponseInputTextParam]:
    if isinstance(content, str):
        return [_text_part(content)] if content else []

    parts: list[ResponseInputTextParam] = []
    for block in content or []:
        if not isinstance(block, dict):
            continue
        match block["type"]:
            case "text":
                if text := block["text"]:
                    parts.append(_text_part(text))
            case "mid_conv_system":
                parts.extend(_system_parts(block.get("content")))
            case unsupported:
                log.warning(
                    f"Dropping unsupported system content block: {unsupported}"
                )
    return parts


def _from_user_turn(
    content: str | Iterable[BetaContentBlockParam],
) -> list[InputItem]:
    if isinstance(content, str):
        return [_message("user", [_text_part(content)])] if content else []

    # The outputs answer the calls of the previous turn, so they come first,
    # and the system text prefaces the user text that follows it
    outputs: list[InputItem] = []
    system: list[InputItem] = []
    parts: list[ResponseInputContentParam] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        match block["type"]:
            case "tool_result":
                outputs.append(_function_call_output(block))
            case "mid_conv_system":
                system.extend(_from_system_turn([block]))
            case _:
                parts.extend(_content_parts(block))

    user = [_message("user", parts)] if parts else []
    return [*outputs, *system, *user]


def _function_call_output(
    block: BetaToolResultBlockParam,
) -> FunctionCallOutputParam:
    parts = _tool_result_parts(block.get("content"))
    is_error = block.get("is_error")

    output: str | list[ResponseInputContentParam]
    texts = [part["text"] for part in parts if part["type"] == "input_text"]
    if len(texts) == len(parts):
        text = "\n".join(texts)
        output = f"Error: {text}" if is_error else text
    else:
        # Images and documents stay in the output of the call they answer
        output = [_text_part("Error:"), *parts] if is_error else parts

    return {
        "type": "function_call_output",
        "call_id": block["tool_use_id"],
        "output": output,
    }


def _tool_result_parts(
    content: str | Iterable[ToolResultContent] | None,
) -> list[ResponseInputContentParam]:
    if isinstance(content, str):
        return [_text_part(content)] if content else []

    parts: list[ResponseInputContentParam] = []
    for block in content or []:
        if not isinstance(block, dict):
            continue
        match block["type"]:
            case "tool_reference":
                # Names a tool for the Anthropic tool search to load
                continue
            case _:
                parts.extend(_content_parts(block))
    return parts


def _content_parts(
    block: BetaContentBlockParam | ToolResultContent,
) -> list[ResponseInputContentParam]:
    if not isinstance(block, dict):
        return []
    match block["type"]:
        case "text":
            return [_text_part(text)] if (text := block["text"]) else []
        case "image":
            return [part] if (part := _image_part(block)) else []
        case "document":
            return _document_parts(block)
        case "search_result":
            return [_text_part(_search_result_text(block))]
        case "compaction":
            return [_text_part(text)] if (text := block.get("content")) else []
        case unsupported:
            log.warning(f"Dropping unsupported content block: {unsupported}")
            return []


def _image_part(block: BetaImageBlockParam) -> ResponseInputImageParam | None:
    source = block["source"]
    match source["type"]:
        case "base64":
            media_type = source.get("media_type") or "image/png"
            url = f"data:{media_type};base64,{source['data']}"
        case "url":
            url = source["url"]
        case "file":
            raise InvalidRequestError(_FILES_API_UNSUPPORTED)
        case unsupported:
            log.warning(f"Dropping image block with source type: {unsupported}")
            return None
    return {"type": "input_image", "image_url": url, "detail": "auto"}


def _document_parts(
    block: BetaRequestDocumentBlockParam,
) -> list[ResponseInputContentParam]:
    source = block["source"]
    match source["type"]:
        case "base64":
            media_type = source.get("media_type") or "application/pdf"
            file: ResponseInputFileParam = {
                "type": "input_file",
                "filename": block.get("title") or "document.pdf",
                "file_data": f"data:{media_type};base64,{source['data']}",
            }
            return [file]
        case "url":
            return [{"type": "input_file", "file_url": source["url"]}]
        case "text":
            return [_text_part(text)] if (text := source["data"]) else []
        case "content":
            return _document_content_parts(source["content"])
        case "file":
            raise InvalidRequestError(_FILES_API_UNSUPPORTED)
        case unsupported:
            log.warning(
                f"Dropping document block with source type: {unsupported}"
            )
            return []


def _document_content_parts(
    content: str | Iterable[BetaContentBlockSourceContentParam],
) -> list[ResponseInputContentParam]:
    if isinstance(content, str):
        return [_text_part(content)] if content else []
    return [part for block in content for part in _content_parts(block)]


def _search_result_text(block: BetaSearchResultBlockParam) -> str:
    text = "\n".join(sub["text"] for sub in block["content"] if sub.get("text"))
    return f"{block['title']}\n{block['source']}\n\n{text}"


def _from_assistant_turn(
    content: str | Iterable[BetaContentBlockParam],
    translation_state: TranslationState,
) -> list[InputItem]:
    if isinstance(content, str):
        return [_message("assistant", content)] if content else []

    # A function call must follow the reasoning that made it, so the blocks
    # keep their order, the adjacent texts joined into one message
    system: list[InputItem] = []
    items: list[InputItem] = []
    texts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        item: InputItem | None = None
        match block["type"]:
            case "text":
                if text := block["text"]:
                    texts.append(text)
            case "compaction":
                if text := block.get("content"):
                    texts.append(text)
            case "tool_use":
                item = {
                    "type": "function_call",
                    "call_id": block["id"],
                    "name": translation_state.to_upstream_tool_name(
                        block["name"]
                    ),
                    "arguments": json.dumps(block.get("input") or {}),
                }
            case "thinking" | "redacted_thinking":
                item = to_reasoning_item(block)
            case "mid_conv_system":
                system.extend(_from_system_turn([block]))
            case unsupported:
                log.warning(
                    f"Dropping unsupported assistant content block: {unsupported}"
                )

        if item is not None:
            items.extend(_assistant_text(texts))
            texts = []
            items.append(item)

    items.extend(_assistant_text(texts))
    # After the turn, the system text could separate a call from its output
    return [*system, *items]


def _assistant_text(texts: list[str]) -> list[InputItem]:
    return [_message("assistant", "\n".join(texts))] if texts else []


def _to_responses_tool(
    tool: BetaToolUnionParam, translation_state: TranslationState
) -> ToolParam | BetaToolUnionParam:
    tool_type = tool.get("type")
    if tool_type is None or tool_type == "custom":
        return _function_tool(cast(BetaToolParam, tool), translation_state)
    if _is_web_search(tool):
        return _web_search_tool(cast(BetaWebSearchTool20250305Param, tool))
    return tool


def _function_tool(
    tool: BetaToolParam, translation_state: TranslationState
) -> FunctionToolParam:
    function: FunctionToolParam = {
        "type": "function",
        "name": translation_state.to_upstream_tool_name(tool["name"]),
        "parameters": _parameters(tool),
        "strict": bool(tool.get("strict")),
    }
    if description := tool.get("description"):
        function["description"] = description
    return function


def _parameters(tool: BetaToolParam) -> dict[str, object]:
    if (schema := tool.get("input_schema")) is None:
        return {"type": "object", "properties": {}}

    # `$schema` is valid JSON Schema, but OpenAI rejects function parameters
    # that contain it
    return {key: value for key, value in schema.items() if key != "$schema"}


def _is_web_search(tool: BetaToolUnionParam) -> bool:
    return (tool.get("type") or "").startswith("web_search_")


def _web_search_tool(
    tool: BetaWebSearchTool20250305Param,
) -> WebSearchToolParam:
    web_search: WebSearchToolParam = {"type": "web_search"}
    if allowed_domains := tool.get("allowed_domains"):
        web_search["filters"] = {"allowed_domains": allowed_domains}
    if location := tool.get("user_location"):
        web_search["user_location"] = {
            "type": "approximate",
            "city": location.get("city"),
            "country": location.get("country"),
            "region": location.get("region"),
            "timezone": location.get("timezone"),
        }
    if tool.get("blocked_domains"):
        log.warning(
            "Dropping web_search blocked_domains: "
            "no Responses API equivalent, the search isn't restricted"
        )
    return web_search


def _to_max_tool_calls(tools: Iterable[BetaToolUnionParam]) -> int | None:
    # `max_tool_calls` caps the calls of all the built-in tools together,
    # which is the cap of a web search when it's the only built-in tool
    searches = [
        cast(BetaWebSearchTool20250305Param, tool)
        for tool in tools
        if _is_web_search(tool)
    ]
    if len(searches) != 1:
        if any(search.get("max_uses") is not None for search in searches):
            log.warning(
                "Dropping web_search max_uses: several web search tools "
                "can't share one Responses API max_tool_calls"
            )
        return None
    return searches[0].get("max_uses")


def _to_tool_choice(
    tool_choice: BetaToolChoiceParam,
    tools: Iterable[BetaToolUnionParam],
    translation_state: TranslationState,
) -> ToolChoice | None:
    match tool_choice["type"]:
        case "auto":
            return "auto"
        case "any":
            return "required"
        case "none":
            return "none"
        case "tool":
            name = tool_choice["name"]
            if any(
                _is_web_search(tool) and tool.get("name") == name
                for tool in tools
            ):
                # The tool is sent as the built-in web search, which a choice
                # can't name
                return {
                    "type": "allowed_tools",
                    "mode": "required",
                    "tools": [{"type": "web_search"}],
                }
            return {
                "type": "function",
                "name": translation_state.to_upstream_tool_name(name),
            }
        case _:
            return None
