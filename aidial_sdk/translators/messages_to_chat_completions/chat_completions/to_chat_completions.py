import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, Self, TypeVar, assert_never, cast

from anthropic.types.beta import (
    BetaCacheControlEphemeralParam as CacheControl,
)
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaContentBlockSourceContentParam,
    BetaImageBlockParam,
    BetaJSONOutputFormatParam,
    BetaMessageParam,
    BetaRequestDocumentBlockParam,
    BetaSearchResultBlockParam,
    BetaToolChoiceParam,
    BetaToolParam,
    BetaToolResultBlockParam,
    BetaToolUnionParam,
)
from anthropic.types.beta.beta_tool_result_block_param import (
    Content as ToolResultContent,
)
from anthropic.types.beta.message_create_params import MessageCreateParams
from openai.types.shared import ReasoningEffort
from pydantic import BaseModel

from aidial_sdk.chat_completion.request import (
    ChatCompletionRequestCustomFields,
    FunctionCall,
    FunctionChoice,
    ImageURL,
    InputFile,
    MessageContentFilePart,
    MessageContentImagePart,
    MessageContentPart,
    MessageContentTextPart,
    MessageCustomFields,
    ResponseFormat,
    ResponseFormatJsonSchema,
    ResponseFormatJsonSchemaObject,
    Role,
    StaticFunction,
    StaticTool,
    StreamOptions,
    ToolCall,
    ToolCustomFields,
)
from aidial_sdk.chat_completion.request import Function as SdkFunction
from aidial_sdk.chat_completion.request import Message as SdkMessage
from aidial_sdk.chat_completion.request import Tool as SdkTool
from aidial_sdk.chat_completion.request import ToolChoice as SdkToolChoice
from aidial_sdk.translators.messages_to_chat_completions.chat_completions.cache_breakpoints import (
    to_dial_cache_breakpoint,
)
from aidial_sdk.translators.messages_to_chat_completions.chat_completions.reasoning import (
    resolve_effort,
)
from aidial_sdk.translators.messages_to_chat_completions.chat_completions.system_turns import (
    visible_messages,
)
from aidial_sdk.translators.messages_to_chat_completions.errors import (
    AnthropicErrorType,
    AnthropicHTTPError,
)
from aidial_sdk.translators.messages_to_chat_completions.translation_state import (
    TranslationState,
)
from aidial_sdk.translators.messages_to_chat_completions.utils.log_config import (
    bedrock_logger as log,
)

_SERVICE_TIERS = {"auto": "auto", "standard_only": "default"}

_FILES_API_UNSUPPORTED = (
    "Files uploaded via Anthropic Files API aren't supported."
)

_Block = TypeVar("_Block")


class DialChatCompletionsRequest(BaseModel):
    # Not the DIAL SDK request model: it validates the values and would reject
    # what the translator passes through (e.g. `reasoning_effort` of `xhigh` and
    # `max`, more than 4 `stop` sequences), turning them into a 400 or a 500.
    model: str
    messages: list[SdkMessage]
    max_completion_tokens: int | None
    custom_fields: ChatCompletionRequestCustomFields | None
    tools: list[SdkTool | StaticTool] | None
    tool_choice: Literal["auto", "none", "required"] | SdkToolChoice | None
    parallel_tool_calls: bool | None
    reasoning_effort: ReasoningEffort
    response_format: ResponseFormat | None
    stop: list[str] | None
    temperature: float | None
    top_p: float | None
    user: str | None
    service_tier: str | None
    stream: bool
    stream_options: StreamOptions | None


@dataclass
class SystemPrompt:
    texts: list[str]
    cache_controls: list[CacheControl]

    @property
    def text(self) -> str:
        return "\n\n".join(self.texts)

    def extend(self, other: Self) -> None:
        self.texts.extend(other.texts)
        self.cache_controls.extend(other.cache_controls)


def to_chat_completions_request(
    req: MessageCreateParams,
    deployment: str,
    translation_state: TranslationState,
) -> DialChatCompletionsRequest:
    _warn_dropped(req)

    configuration = (
        {"enable_citations": True}
        if _any_citations_enabled(req["messages"])
        else None
    )
    cache_breakpoint = (
        to_dial_cache_breakpoint([control])
        if (control := req.get("cache_control")) is not None
        else None
    )
    stream = bool(req.get("stream"))

    return DialChatCompletionsRequest(
        model=deployment,
        messages=_to_dial_messages(req, translation_state),
        custom_fields=(
            ChatCompletionRequestCustomFields(
                configuration=configuration, cache_breakpoint=cache_breakpoint
            )
            if configuration is not None or cache_breakpoint is not None
            else None
        ),
        tools=_convert_tools(req.get("tools"), translation_state) or None,
        tool_choice=_convert_tool_choice(
            req.get("tool_choice"), translation_state
        ),
        parallel_tool_calls=_convert_parallel_tool_calls(
            req.get("tool_choice")
        ),
        reasoning_effort=resolve_effort(req),
        response_format=_convert_response_format(req),
        stop=_convert_stop(req),
        max_completion_tokens=req.get("max_tokens"),
        temperature=req.get("temperature"),
        top_p=req.get("top_p"),
        user=(req.get("metadata", {}).get("user_id") or None)
        if req.get("metadata")
        else None,
        service_tier=_convert_service_tier(req),
        stream=stream,
        stream_options=StreamOptions(include_usage=True) if stream else None,
    )


def _to_dial_messages(
    req: MessageCreateParams,
    translation_state: TranslationState,
) -> list[SdkMessage]:
    messages: list[SdkMessage] = []

    system = _collect_system(req)
    if system.texts:
        system_message = SdkMessage(role=Role.SYSTEM, content=system.text)
        _add_breakpoint_to_message(system_message, system.cache_controls)
        messages.append(system_message)

    for message in req["messages"]:
        match message["role"]:
            case "user":
                converted = _convert_user_message(message["content"])
            case "assistant":
                converted = _convert_assistant_message(
                    message["content"], translation_state
                )
            case "system":
                continue
            case unsupported:
                raise AnthropicHTTPError(
                    AnthropicErrorType.INVALID_REQUEST,
                    f"Unsupported message role: {unsupported}",
                )

        controls = _cache_controls(message["content"])
        for converted_message in converted:
            _add_breakpoint_to_message(converted_message, controls)
        messages.extend(converted)

    return messages


def _warn_dropped(req: MessageCreateParams) -> None:
    unsupported = (
        "top_k",
        "compaction",
        "mcp_servers",
        "container",
        "inference_geo",
        "context_management",
    )
    if params := [key for key in unsupported if key in req]:
        log.warning(
            "Ignoring Anthropic Messages API parameters that have no "
            f"Chat Completions equivalent: {', '.join(params)}."
        )


def _convert_service_tier(req: MessageCreateParams) -> str | None:
    if (tier := req.get("service_tier")) is None:
        return None
    return _SERVICE_TIERS.get(tier)


def _convert_stop(req: MessageCreateParams) -> list[str] | None:
    if (stop_sequences := req.get("stop_sequences")) is None:
        return None
    return list(stop_sequences)


def _convert_response_format(req: MessageCreateParams) -> ResponseFormat | None:
    output_format: BetaJSONOutputFormatParam | None = (
        req.get("output_config") or {}
    ).get("format")
    if output_format is None:
        return None
    if output_format.get("type") != "json_schema":
        log.warning(
            "Dropping unsupported output_config.format type: "
            f"{output_format.get('type')}"
        )
        return None
    schema = output_format.get("schema")
    if not schema:
        log.warning("Dropping output_config.format: missing 'schema'")
        return None
    return ResponseFormatJsonSchema(
        type="json_schema",
        json_schema=ResponseFormatJsonSchemaObject(
            name="response",
            schema=schema,
            strict=True,
        ),
    )


def _cache_controls(
    content: str | Iterable[BetaContentBlockParam] | None,
) -> list[CacheControl]:
    return [
        control
        for block in _blocks(content)
        if isinstance(block, dict) and (control := block.get("cache_control"))
    ]


def _add_breakpoint_to_message(
    message: SdkMessage,
    controls: list[CacheControl],
) -> None:
    breakpoint = to_dial_cache_breakpoint(controls)
    if breakpoint is None:
        return
    if message.custom_fields is None:
        message.custom_fields = MessageCustomFields(cache_breakpoint=breakpoint)
        return
    current = message.custom_fields.cache_breakpoint
    if current and (current.expire_at or "") > (breakpoint.expire_at or ""):
        return
    message.custom_fields.cache_breakpoint = breakpoint


def _add_breakpoint_to_tool(
    tool: SdkTool,
    controls: list[CacheControl],
) -> None:
    if (breakpoint := to_dial_cache_breakpoint(controls)) is not None:
        tool.custom_fields = ToolCustomFields(cache_breakpoint=breakpoint)


def _any_citations_enabled(messages: Iterable[BetaMessageParam]) -> bool:
    for message in messages:
        for block in _blocks(message["content"]):
            if not isinstance(block, dict):
                continue
            if (
                block["type"] == "document"
                and (citations := block.get("citations"))
                and citations.get("enabled")
            ):
                return True
    return False


def _blocks(content: str | Iterable[_Block] | None) -> list[_Block]:
    if content is None or isinstance(content, str):
        return []
    return list(content)


def _system_text(
    content: str | Iterable[BetaContentBlockParam] | None,
) -> SystemPrompt:
    if isinstance(content, str):
        return SystemPrompt(
            texts=[content] if content else [], cache_controls=[]
        )

    texts: list[str] = []
    for block in _blocks(content):
        if not isinstance(block, dict):
            continue
        match block["type"]:
            case "text":
                if text := block.get("text"):
                    texts.append(text)
            case "mid_conv_system":
                continue
            case unsupported:
                log.warning(
                    f"Dropping unsupported system content block: {unsupported}"
                )
    return SystemPrompt(
        texts=texts, cache_controls=_cache_controls(content) if texts else []
    )


def _collect_system(req: MessageCreateParams) -> SystemPrompt:
    system = _system_text(req.get("system"))

    for message in visible_messages(req["messages"]):
        if message["role"] == "system":
            system.extend(_system_text(message["content"]))

        for block in _blocks(message["content"]):
            if isinstance(block, dict) and block["type"] == "mid_conv_system":
                if control := block.get("cache_control"):
                    system.cache_controls.append(control)
                system.extend(_system_text(block.get("content")))

    return system


def _convert_user_message(
    content: str | Iterable[BetaContentBlockParam],
) -> list[SdkMessage]:
    if isinstance(content, str):
        if not content:
            return []
        return [SdkMessage(role=Role.USER, content=content)]

    tool_messages: list[SdkMessage] = []
    parts: list[MessageContentPart] = []

    for block in _blocks(content):
        if not isinstance(block, dict):
            continue
        match block["type"]:
            case "tool_result":
                tool_messages.append(_tool_result_message(block))
                parts.extend(_tool_result_parts(block.get("content")))
            case "text":
                if block.get("text"):
                    parts.append(
                        MessageContentTextPart(
                            type="text", text=block.get("text")
                        )
                    )
            case "image":
                if part := _image_part(block):
                    parts.append(part)
            case "document":
                parts.extend(_document_parts(block))
            case "search_result":
                parts.append(
                    MessageContentTextPart(
                        type="text", text=_search_result_text(block)
                    )
                )
            case "compaction":
                if text := block.get("content"):
                    parts.append(MessageContentTextPart(type="text", text=text))
            case "mid_conv_system":
                continue
            case unsupported:
                log.warning(
                    f"Dropping unsupported user content block: {unsupported}"
                )

    if parts:
        tool_messages.append(SdkMessage(role=Role.USER, content=parts))
    return tool_messages


def _tool_result_message(block: BetaToolResultBlockParam) -> SdkMessage:
    text = _tool_result_text(block.get("content"))
    return SdkMessage(
        role=Role.TOOL,
        tool_call_id=block.get("tool_use_id"),
        content=f"Error: {text}" if block.get("is_error") else text,
    )


def _tool_result_text(content: str | Iterable[ToolResultContent] | None) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(
        text
        for sub in _blocks(content)
        if isinstance(sub, dict)
        and sub["type"] == "text"
        and (text := sub.get("text"))
    )


def _tool_result_parts(
    content: str | Iterable[ToolResultContent] | None,
) -> list[MessageContentPart]:
    parts: list[MessageContentPart] = []
    for sub in _blocks(content):
        if not isinstance(sub, dict):
            continue
        match sub["type"]:
            case "image":
                if part := _image_part(sub):
                    parts.append(part)
            case "document":
                parts.extend(_document_parts(sub))
            case "text":
                pass  # sent as the tool message content
            case unsupported:
                log.warning(
                    f"Dropping unsupported tool_result content block: {unsupported}"
                )
    return parts


def _search_result_text(block: BetaSearchResultBlockParam) -> str:
    text = "\n".join(sub["text"] for sub in block["content"] if sub.get("text"))
    return f"{block['title']}\n{block['source']}\n\n{text}"


def _convert_assistant_message(
    content: str | Iterable[BetaContentBlockParam],
    translation_state: TranslationState,
) -> list[SdkMessage]:
    if isinstance(content, str):
        return (
            [SdkMessage(role=Role.ASSISTANT, content=content)]
            if content
            else []
        )

    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []

    for block in content:
        if not isinstance(block, dict):
            continue
        match block["type"]:
            case "text":
                if block.get("text"):
                    text_parts.append(block.get("text"))
            case "compaction":
                if text := block.get("content"):
                    text_parts.append(text)
            case "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.get("id") or "",
                        type="function",
                        function=FunctionCall(
                            name=translation_state.to_upstream_tool_name(
                                block.get("name") or ""
                            ),
                            arguments=json.dumps(block.get("input") or {}),
                        ),
                    )
                )
            case "thinking" | "redacted_thinking" | "mid_conv_system":
                continue
            case unsupported:
                log.warning(
                    f"Dropping unsupported assistant content block: {unsupported}"
                )

    if not text_parts and not tool_calls:
        return []

    return [
        SdkMessage(
            role=Role.ASSISTANT,
            content="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls or None,
        )
    ]


def _image_part(block: BetaImageBlockParam) -> MessageContentPart | None:
    source = block["source"]
    match source["type"]:
        case "base64":
            media_type = source.get("media_type") or "image/png"
            return MessageContentImagePart(
                type="image_url",
                image_url=ImageURL(
                    url=f"data:{media_type};base64,{source['data']}"
                ),
            )
        case "url":
            return MessageContentImagePart(
                type="image_url", image_url=ImageURL(url=source["url"])
            )
        case "file":
            raise AnthropicHTTPError(
                AnthropicErrorType.INVALID_REQUEST, _FILES_API_UNSUPPORTED
            )
        case unsupported:
            log.warning(f"Dropping image block with source type: {unsupported}")
            return None


def _document_parts(
    block: BetaRequestDocumentBlockParam,
) -> list[MessageContentPart]:
    source = block["source"]
    filename = block.get("title") or "document.pdf"
    match source["type"]:
        case "base64":
            media_type = source.get("media_type") or "application/pdf"
            data = source["data"]
            return [
                MessageContentFilePart(
                    type="file",
                    file=InputFile(
                        filename=filename,
                        file_data=f"data:{media_type};base64,{data}",
                    ),
                )
            ]
        case "text":
            if not (text_data := source["data"]):
                return []
            return [MessageContentTextPart(type="text", text=text_data)]
        case "content":
            return _document_content_parts(source["content"])
        case "url":
            raise AnthropicHTTPError(
                AnthropicErrorType.INVALID_REQUEST,
                "Unsupported document source type 'url': "
                "a Chat Completions file part has no URL field",
            )
        case "file":
            raise AnthropicHTTPError(
                AnthropicErrorType.INVALID_REQUEST, _FILES_API_UNSUPPORTED
            )
        case unsupported:
            log.warning(
                f"Dropping document block with source type: {unsupported}"
            )
            return []


def _document_content_parts(
    content: str | Iterable[BetaContentBlockSourceContentParam],
) -> list[MessageContentPart]:
    if isinstance(content, str):
        return (
            [MessageContentTextPart(type="text", text=content)]
            if content
            else []
        )

    parts: list[MessageContentPart] = []
    for sub in _blocks(content):
        if not isinstance(sub, dict):
            continue
        match sub["type"]:
            case "text":
                if sub.get("text"):
                    parts.append(
                        MessageContentTextPart(type="text", text=sub["text"])
                    )
            case "image":
                if part := _image_part(sub):
                    parts.append(part)
    return parts


def _convert_tools(
    tools: Iterable[BetaToolUnionParam] | None,
    translation_state: TranslationState,
) -> list[SdkTool | StaticTool]:
    if not tools:
        return []
    result: list[SdkTool | StaticTool] = []
    for tool in tools:
        if tool.get("type") in (None, "custom"):
            result.append(
                _function_tool(cast(BetaToolParam, tool), translation_state)
            )
        else:
            result.append(_static_tool(tool))
    return result


def _function_tool(
    tool: BetaToolParam, translation_state: TranslationState
) -> SdkTool:
    sdk_tool = SdkTool(
        type="function",
        function=SdkFunction(
            name=translation_state.to_upstream_tool_name(tool["name"]),
            description=tool.get("description") or None,
            parameters=_parameters(tool),
            strict=bool(tool.get("strict")),
        ),
    )
    _add_breakpoint_to_tool(
        sdk_tool,
        [control] if (control := tool.get("cache_control")) else [],
    )
    return sdk_tool


def _static_tool(tool: BetaToolUnionParam) -> StaticTool:
    return StaticTool(
        type="static_function",
        static_function=StaticFunction(
            name=_static_tool_name(tool), configuration=dict(tool)
        ),
    )


def _static_tool_name(tool: BetaToolUnionParam) -> str:
    if "name" in tool:
        return tool["name"]
    if "mcp_server_name" in tool:
        return tool["mcp_server_name"]
    assert_never(tool)


def _parameters(tool: BetaToolParam) -> dict[str, object]:
    if (schema := tool.get("input_schema")) is None:
        return {"type": "object", "properties": {}}

    # `$schema` is valid JSON Schema, but some providers (e.g. Gemini) reject
    # function parameters that contain it.
    return {key: value for key, value in schema.items() if key != "$schema"}


def _convert_tool_choice(
    tool_choice: BetaToolChoiceParam | None,
    translation_state: TranslationState,
) -> Literal["auto", "none", "required"] | SdkToolChoice | None:
    if tool_choice is None:
        return None
    match tool_choice["type"]:
        case "auto":
            return "auto"
        case "any":
            return "required"
        case "none":
            return "none"
        case "tool":
            return SdkToolChoice(
                type="function",
                function=FunctionChoice(
                    name=translation_state.to_upstream_tool_name(
                        tool_choice["name"]
                    )
                ),
            )
        case _:
            return None


def _convert_parallel_tool_calls(
    tool_choice: BetaToolChoiceParam | None,
) -> bool | None:
    if not tool_choice or "disable_parallel_tool_use" not in tool_choice:
        return None
    return not bool(tool_choice.get("disable_parallel_tool_use"))
