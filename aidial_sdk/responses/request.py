from collections.abc import Mapping
from enum import Enum
from typing import Any, Literal, Self

import fastapi

from aidial_sdk._pydantic import (
    Field,
    PositiveInt,
    StrictBool,
    StrictInt,
    StrictStr,
)
from aidial_sdk._pydantic._compat import model_validator
from aidial_sdk.chat_completion.request import Temperature, TopP
from aidial_sdk.deployment.from_request_mixin import (
    FromRequestDeploymentMixin,
    FromRequestMixin,
)
from aidial_sdk.exceptions import InvalidRequestError, RequestValidationError
from aidial_sdk.responses.enums import ItemStatus, MessagePhase
from aidial_sdk.utils.pydantic import ExtraAllowModel


class InputRole(str, Enum):
    SYSTEM = "system"
    DEVELOPER = "developer"
    USER = "user"
    ASSISTANT = "assistant"


# The `type` values that have a dedicated model below. `RawItem` refuses them,
# so that a malformed known item is a validation error rather than silently
# becoming a `RawItem`, and the union resolves the same way in pydantic v1
# (first match wins) and v2 (best match wins).
_MODELLED_TYPES = frozenset(
    {
        "message",
        "function_call",
        "function_call_output",
        "custom_tool_call",
        "custom_tool_call_output",
        "reasoning",
        "item_reference",
        "input_text",
        "input_image",
        "input_file",
        "input_audio",
        "output_text",
        "refusal",
    }
)


class RawItem(ExtraAllowModel):
    """
    An input item or content part of a type the SDK doesn't model,
    preserved verbatim in `raw`.

    Unlike `chat_completion`, an unknown shape is not a validation error:
    Responses grows new item types faster than the SDK can track them.
    It's produced by parsing: the validator takes the item as it appears
    on the wire and stores it in `raw`, so don't construct it from `raw`.
    """

    type: StrictStr
    raw: dict[str, Any]

    @model_validator(mode="before")
    @classmethod
    def wrap_item(cls, data: Any) -> Any:
        if not isinstance(data, Mapping):
            return data

        item_type = data.get("type")
        if isinstance(item_type, str) and item_type in _MODELLED_TYPES:
            raise ValueError(
                f"The item of type {item_type!r} is expected to match its model"
            )

        return {"type": item_type, "raw": dict(data)}

    @property
    def id(self) -> str | None:
        item_id = self.raw.get("id")
        return item_id if isinstance(item_id, str) else None


class InputTextPart(ExtraAllowModel):
    type: Literal["input_text"]
    text: StrictStr


class InputImagePart(ExtraAllowModel):
    type: Literal["input_image"]
    image_url: StrictStr | None = None
    file_id: StrictStr | None = None
    detail: StrictStr | None = None


class InputFilePart(ExtraAllowModel):
    type: Literal["input_file"]
    file_url: StrictStr | None = None
    file_data: StrictStr | None = None
    file_id: StrictStr | None = None
    filename: StrictStr | None = None


class InputAudio(ExtraAllowModel):
    data: StrictStr
    format: StrictStr


class InputAudioPart(ExtraAllowModel):
    type: Literal["input_audio"]
    input_audio: InputAudio


class OutputTextPart(ExtraAllowModel):
    type: Literal["output_text"]
    text: StrictStr
    annotations: list[dict[str, Any]] | None = None
    logprobs: list[dict[str, Any]] | None = None


class RefusalContentPart(ExtraAllowModel):
    type: Literal["refusal"]
    refusal: StrictStr


InputContentPart = (
    InputTextPart
    | InputImagePart
    | InputFilePart
    | InputAudioPart
    | OutputTextPart
    | RefusalContentPart
    | RawItem
)


class InputMessage(ExtraAllowModel):
    # The legacy shape `{"role": ..., "content": ...}` carries no `type`
    type: Literal["message"] = "message"
    role: InputRole
    content: StrictStr | list[InputContentPart]
    status: ItemStatus | None = None
    id: StrictStr | None = None
    # Sent back on assistant messages, as the response produced it
    phase: MessagePhase | None = None

    def text(self) -> str:
        """
        Returns the concatenation of all `input_text` and `output_text` parts
        of the message, or the content itself if it's a string.
        Returns an empty string if there is no text.

        Unlike `chat_completion.Message.text()`, it never raises:
        in Responses a list of parts is the common case.
        Use `content` when the structure matters.
        """
        if isinstance(self.content, str):
            return self.content

        return "".join(
            part.text
            for part in self.content
            if isinstance(part, InputTextPart | OutputTextPart)
        )

    def images(self) -> list[InputImagePart]:
        """Returns the `input_image` parts of the message."""
        if isinstance(self.content, str):
            return []

        return [
            part for part in self.content if isinstance(part, InputImagePart)
        ]


class FunctionCallItem(ExtraAllowModel):
    type: Literal["function_call"]
    call_id: StrictStr
    name: StrictStr
    arguments: StrictStr
    status: ItemStatus | None = None
    id: StrictStr | None = None


class FunctionCallOutputItem(ExtraAllowModel):
    type: Literal["function_call_output"]
    call_id: StrictStr
    output: StrictStr | list[InputContentPart]
    status: ItemStatus | None = None
    id: StrictStr | None = None


class CustomToolCallItem(ExtraAllowModel):
    type: Literal["custom_tool_call"]
    call_id: StrictStr
    name: StrictStr
    input: StrictStr
    id: StrictStr | None = None


class CustomToolCallOutputItem(ExtraAllowModel):
    type: Literal["custom_tool_call_output"]
    call_id: StrictStr
    output: StrictStr | list[InputContentPart]
    id: StrictStr | None = None


class ReasoningInputItem(ExtraAllowModel):
    type: Literal["reasoning"]
    id: StrictStr
    summary: list[dict[str, Any]]
    content: list[dict[str, Any]] | None = None
    encrypted_content: StrictStr | None = None
    status: ItemStatus | None = None


class ItemReference(ExtraAllowModel):
    # `type` is optional in `openai`'s `ItemReference`
    type: Literal["item_reference"] | None = "item_reference"
    id: StrictStr

    @model_validator(mode="before")
    @classmethod
    def refuse_legacy_messages(cls, data: Any) -> Any:
        # Both shapes may lack `type`: one with a `role` is a legacy message,
        # so a malformed one is a validation error, not a reference to its `id`
        if (
            isinstance(data, Mapping)
            and data.get("type") is None
            and "role" in data
        ):
            raise ValueError(
                "The item with a 'role' is expected to be a message"
            )
        return data


InputItem = (
    InputMessage
    | FunctionCallItem
    | FunctionCallOutputItem
    | CustomToolCallItem
    | CustomToolCallOutputItem
    | ReasoningInputItem
    | ItemReference
    | RawItem
)


# The tool types with a dedicated model below, see `_MODELLED_TYPES`
_MODELLED_TOOL_TYPES = frozenset({"function", "custom"})


class FunctionTool(ExtraAllowModel):
    type: Literal["function"]
    name: StrictStr
    parameters: dict[str, Any] | None = None
    strict: StrictBool | None = None
    description: StrictStr | None = None


class CustomTool(ExtraAllowModel):
    type: Literal["custom"]
    name: StrictStr
    description: StrictStr | None = None
    format: dict[str, Any] | None = None


class Tool(ExtraAllowModel):
    """
    A tool of a type the SDK doesn't model (`web_search`, `mcp`, ...),
    all of its fields are kept as extras.
    """

    type: StrictStr

    @model_validator(mode="before")
    @classmethod
    def refuse_modelled_types(cls, data: Any) -> Any:
        if isinstance(data, Mapping):
            tool_type = data.get("type")
            if isinstance(tool_type, str) and tool_type in _MODELLED_TOOL_TYPES:
                raise ValueError(
                    f"The tool of type {tool_type!r} "
                    "is expected to match its model"
                )
        return data


class ToolChoice(ExtraAllowModel):
    """
    `{"type": "function", "name": ...}`, `{"type": "allowed_tools", ...}`,
    `{"type": "web_search_preview"}` and the like.
    """

    type: StrictStr
    name: StrictStr | None = None


class TextConfig(ExtraAllowModel):
    format: dict[str, Any] | None = None
    verbosity: StrictStr | None = None


class ReasoningConfig(ExtraAllowModel):
    effort: StrictStr | None = None
    summary: StrictStr | None = None


class StreamOptions(ExtraAllowModel):
    include_obfuscation: StrictBool | None = None


class ConversationRef(ExtraAllowModel):
    id: StrictStr


class ResponsesRequest(ExtraAllowModel):
    model: StrictStr | None = None
    input: StrictStr | list[InputItem]
    instructions: StrictStr | None = None

    tools: list[FunctionTool | CustomTool | Tool] | None = None
    tool_choice: Literal["auto", "none", "required"] | ToolChoice | None = None
    parallel_tool_calls: StrictBool | None = None
    max_tool_calls: PositiveInt | None = None

    stream: StrictBool = False
    stream_options: StreamOptions | None = None

    text: TextConfig | None = None
    reasoning: ReasoningConfig | None = None

    temperature: Temperature | None = None
    top_p: TopP | None = None
    top_logprobs: StrictInt | None = None
    max_output_tokens: PositiveInt | None = None
    truncation: Literal["auto", "disabled"] | None = None
    include: list[StrictStr] | None = None
    metadata: dict[StrictStr, StrictStr] | None = None
    user: StrictStr | None = None
    prompt_cache_key: StrictStr | None = None
    safety_identifier: StrictStr | None = None

    # Declared only so that they can be rejected: a stateless deployment
    # has no response store to honour them with
    store: StrictBool | None = None
    background: StrictBool | None = None
    previous_response_id: StrictStr | None = None
    conversation: StrictStr | ConversationRef | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_stateful_fields(cls, data: Any) -> Any:
        if not isinstance(data, Mapping):
            return data

        stateful = {
            "store": data.get("store") is True,
            "background": data.get("background") is True,
            "previous_response_id": data.get("previous_response_id")
            is not None,
            "conversation": data.get("conversation") is not None,
        }
        for field, is_set in stateful.items():
            if is_set:
                raise RequestValidationError(
                    f"The request field {field!r} is not supported: "
                    "the deployment doesn't store responses"
                )

        return data

    @property
    def input_items(self) -> list[InputItem]:
        """
        The input as a list of items. A string input is normalized
        to a single user message.
        """
        if isinstance(self.input, str):
            return [
                InputMessage(
                    role=InputRole.USER,
                    content=[InputTextPart(type="input_text", text=self.input)],
                )
            ]
        return self.input

    @property
    def messages(self) -> list[InputMessage]:
        """The `message` items of the input, in order."""
        return [
            item for item in self.input_items if isinstance(item, InputMessage)
        ]

    @property
    def user_messages(self) -> list[InputMessage]:
        """The messages of the input with the `user` role, in order."""
        return [
            message
            for message in self.messages
            if message.role == InputRole.USER
        ]


class RequestContext(FromRequestDeploymentMixin):
    """
    The DIAL side of a request: the api key, the deployment id, the headers
    and the rest of `FromRequestDeploymentMixin`. It's parsed from the request
    headers, the body is not read.
    """

    @staticmethod
    async def get_request_body(request: fastapi.Request) -> dict:
        return {}


class Request(ResponsesRequest, FromRequestMixin):
    """
    The request body, parsed as is, with the DIAL side of the request
    kept apart in `context`, so that no body field can collide with it.
    """

    context: RequestContext = Field(..., exclude=True)

    @classmethod
    async def from_request(
        cls,
        request: fastapi.Request,
        deployment_id: str | None,
        base_url: str | None,
    ) -> Self:
        context = await RequestContext.from_request(
            request, deployment_id, base_url
        )

        body = await cls.get_request_body(request)
        if "context" in body:
            raise InvalidRequestError("The request field 'context' is reserved")

        return cls(**body, context=context)

    @staticmethod
    async def get_request_body(request: fastapi.Request) -> dict:
        return await FromRequestDeploymentMixin.get_request_body(request)
