from enum import Enum
from typing import Any, Dict, List, Literal, Mapping, Optional, Union

from typing_extensions import Annotated, assert_never

from aidial_sdk._pydantic import (
    PYDANTIC_V2,
    Field,
    PositiveInt,
    StrictBool,
    StrictInt,
    StrictStr,
)
from aidial_sdk._pydantic._compat import model_validator
from aidial_sdk.chat_completion.enums import Status
from aidial_sdk.deployment.from_request_mixin import FromRequestDeploymentMixin
from aidial_sdk.exceptions import InvalidRequestError
from aidial_sdk.utils.pydantic import ExtraAllowModel, IgnoreIndex


class Attachment(ExtraAllowModel, IgnoreIndex):
    type: Optional[StrictStr] = "text/markdown"
    title: Optional[StrictStr] = None
    data: Optional[StrictStr] = None
    url: Optional[StrictStr] = None
    reference_type: Optional[StrictStr] = None
    reference_url: Optional[StrictStr] = None

    @model_validator(mode="before")
    @classmethod
    def check_data_or_url(cls, values: Any):
        data, url = values.get("data"), values.get("url")

        if data is None and url is None:
            raise ValueError(
                "Attachment must have either 'data' or 'url', but it's missing both"
            )
        if data is not None and url is not None:
            raise ValueError(
                "Attachment must have either 'data' or 'url', but it has both"
            )

        return values


class Stage(ExtraAllowModel, IgnoreIndex):
    name: StrictStr
    status: Status
    content: Optional[StrictStr] = None
    attachments: Optional[List[Attachment]] = None


class CustomContent(ExtraAllowModel):
    stages: Optional[List[Stage]] = None
    attachments: Optional[List[Attachment]] = None
    state: Optional[Any] = None
    form_value: Optional[Any] = None
    form_schema: Optional[Any] = None


class FunctionCall(ExtraAllowModel):
    name: str
    arguments: str


class ToolCall(ExtraAllowModel, IgnoreIndex):
    id: StrictStr
    type: Literal["function"]
    function: FunctionCall


class Role(str, Enum):
    SYSTEM = "system"
    DEVELOPER = "developer"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"
    TOOL = "tool"


class ImageURL(ExtraAllowModel):
    url: StrictStr
    detail: Optional[Literal["auto", "low", "high"]] = None


class MessageContentImagePart(ExtraAllowModel):
    type: Literal["image_url"]
    image_url: ImageURL


class MessageContentTextPart(ExtraAllowModel):
    type: Literal["text"]
    text: StrictStr


class MessageContentRefusalPart(ExtraAllowModel):
    type: Literal["refusal"]
    refusal: StrictStr


MessageContentPart = Union[
    MessageContentTextPart,
    MessageContentImagePart,
    MessageContentRefusalPart,
]


class CacheBreakpoint(ExtraAllowModel):
    expire_at: Optional[StrictStr] = None


class MessageCustomFields(ExtraAllowModel):
    cache_breakpoint: Optional[CacheBreakpoint] = None


class Message(ExtraAllowModel):
    role: Role
    content: Optional[Union[StrictStr, List[MessageContentPart]]] = None
    custom_content: Optional[CustomContent] = None
    custom_fields: Optional[MessageCustomFields] = None
    name: Optional[StrictStr] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[StrictStr] = None
    function_call: Optional[FunctionCall] = None
    refusal: Optional[StrictStr] = None

    def text(self) -> str:
        """
        Returns content of the message only if it's present as a string.
        Otherwise, throws an invalid request exception.
        """

        def _error_message(actual: str) -> str:
            return f"Unable to retrieve text content of the message: the actual content is {actual}."

        if self.content is None:
            raise InvalidRequestError(_error_message("null or missing"))
        elif isinstance(self.content, str):
            return self.content
        elif isinstance(self.content, list):
            raise InvalidRequestError(_error_message("a list of content parts"))
        else:
            assert_never(self.content)


class Addon(ExtraAllowModel):
    name: Optional[StrictStr] = None
    url: Optional[StrictStr] = None


class Function(ExtraAllowModel):
    name: StrictStr
    strict: bool = False
    description: Optional[StrictStr] = None
    parameters: Optional[Dict] = None


Temperature = Annotated[float, Field(ge=0, le=2)]
TopP = Annotated[float, Field(ge=0, le=1)]
N = Annotated[int, Field(ge=1, le=128)]
Stop = Annotated[List[StrictStr], Field(max_length=4)]
Penalty = Annotated[float, Field(ge=-2, le=2)]


class ToolCustomFields(ExtraAllowModel):
    cache_breakpoint: Optional[CacheBreakpoint] = None


class Tool(ExtraAllowModel):
    type: Literal["function"]
    function: Function
    custom_fields: Optional[ToolCustomFields] = None


class StaticFunction(ExtraAllowModel):
    name: str
    description: Optional[str] = None
    configuration: Optional[Dict[str, Any]] = None


class StaticTool(ExtraAllowModel):
    type: Literal["static_function"]
    static_function: StaticFunction


class FunctionChoice(ExtraAllowModel):
    name: StrictStr


class ToolChoice(ExtraAllowModel):
    type: Literal["function"]
    function: FunctionChoice


class ResponseFormatText(ExtraAllowModel):
    type: Literal["text"]


class ResponseFormatJsonObject(ExtraAllowModel):
    type: Literal["json_object"]


if PYDANTIC_V2:
    import pydantic as pyd2


class ResponseFormatJsonSchemaObject(ExtraAllowModel):
    description: Optional[StrictStr] = None
    name: StrictStr
    schema_: Dict[str, Any] = Field(..., alias="schema")
    strict: Optional[StrictBool] = False

    if PYDANTIC_V2:

        @pyd2.model_serializer(mode="wrap")
        def serializer(
            self, nxt: pyd2.SerializerFunctionWrapHandler
        ) -> Dict[str, Any]:
            ret = nxt(self)
            ret["schema"] = ret["schema_"]
            del ret["schema_"]
            return ret

    else:

        def dict(self, *args, **kwargs):
            kwargs["by_alias"] = True
            return super().dict(*args, **kwargs)  # type: ignore


class ResponseFormatJsonSchema(ExtraAllowModel):
    type: Literal["json_schema"]
    json_schema: ResponseFormatJsonSchemaObject


class StreamOptions(ExtraAllowModel):
    include_usage: Optional[bool]


ResponseFormat = Union[
    ResponseFormatText,
    ResponseFormatJsonObject,
    ResponseFormatJsonSchema,
]


class AzureChatCompletionRequest(ExtraAllowModel):
    model: Optional[StrictStr] = None
    messages: List[Message]
    functions: Optional[List[Function]] = None
    function_call: Optional[Union[Literal["auto", "none"], FunctionChoice]] = (
        None
    )
    tools: Optional[List[Union[Tool, StaticTool]]] = None
    tool_choice: Optional[
        Union[Literal["auto", "none", "required"], ToolChoice]
    ] = None
    stream: bool = False
    stream_options: Optional[StreamOptions] = None
    temperature: Optional[Temperature] = None
    top_p: Optional[TopP] = None
    n: Optional[N] = None
    stop: Optional[Union[StrictStr, Stop]] = None
    max_tokens: Optional[PositiveInt] = None
    max_completion_tokens: Optional[PositiveInt] = None
    presence_penalty: Optional[Penalty] = None
    frequency_penalty: Optional[Penalty] = None
    logit_bias: Optional[Mapping[int, float]] = None
    user: Optional[StrictStr] = None
    seed: Optional[StrictInt] = None
    logprobs: Optional[StrictBool] = None
    top_logprobs: Optional[StrictInt] = None
    response_format: Optional[ResponseFormat] = None
    parallel_tool_calls: Optional[StrictBool] = None


class ChatCompletionRequestCustomFields(ExtraAllowModel):
    configuration: Optional[Dict[str, Any]] = None


class ChatCompletionRequest(AzureChatCompletionRequest):
    addons: Optional[List[Addon]] = None
    max_prompt_tokens: Optional[PositiveInt] = None
    custom_fields: Optional[ChatCompletionRequestCustomFields] = None


class Request(ChatCompletionRequest, FromRequestDeploymentMixin):
    pass
