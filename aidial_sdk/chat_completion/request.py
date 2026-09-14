from collections.abc import Mapping
from enum import Enum
from typing import Annotated, Any, Literal

from typing_extensions import assert_never

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
    type: StrictStr | None = "text/markdown"
    title: StrictStr | None = None
    data: StrictStr | None = None
    url: StrictStr | None = None
    reference_type: StrictStr | None = None
    reference_url: StrictStr | None = None

    @model_validator(mode="after")
    def check_data_or_url(self) -> "Attachment":
        if self.data is None and self.url is None:
            raise ValueError(
                "Attachment must have either 'data' or 'url', but it's missing both"
            )
        if self.data is not None and self.url is not None:
            raise ValueError(
                "Attachment must have either 'data' or 'url', but it has both"
            )

        return self


class Stage(ExtraAllowModel, IgnoreIndex):
    name: StrictStr
    status: Status
    content: StrictStr | None = None
    attachments: list[Attachment] | None = None


class CustomContent(ExtraAllowModel):
    stages: list[Stage] | None = None
    attachments: list[Attachment] | None = None
    state: dict | None = None
    form_value: Any | None = None
    form_schema: Any | None = None


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
    detail: Literal["auto", "low", "high"] | None = None


class PromptCacheBreakpoint(ExtraAllowModel):
    mode: Literal["explicit"]


class MessageContentImagePart(ExtraAllowModel):
    type: Literal["image_url"]
    image_url: ImageURL
    prompt_cache_breakpoint: PromptCacheBreakpoint | None = None


class MessageContentTextPart(ExtraAllowModel):
    type: Literal["text"]
    text: StrictStr
    prompt_cache_breakpoint: PromptCacheBreakpoint | None = None


class InputFile(ExtraAllowModel):
    file_data: StrictStr | None = None
    file_id: StrictStr | None = None
    filename: StrictStr | None = None


class MessageContentFilePart(ExtraAllowModel):
    type: Literal["file"]
    file: InputFile
    prompt_cache_breakpoint: PromptCacheBreakpoint | None = None


class InputAudio(ExtraAllowModel):
    data: StrictStr
    format: Literal["wav", "mp3"] | StrictStr


class MessageContentAudioPart(ExtraAllowModel):
    type: Literal["input_audio"]
    input_audio: InputAudio
    prompt_cache_breakpoint: PromptCacheBreakpoint | None = None


class MessageContentRefusalPart(ExtraAllowModel):
    type: Literal["refusal"]
    refusal: StrictStr


MessageContentPart = (
    MessageContentTextPart
    | MessageContentImagePart
    | MessageContentFilePart
    | MessageContentAudioPart
    | MessageContentRefusalPart
)


class CacheBreakpoint(ExtraAllowModel):
    expire_at: StrictStr | None = None


class MessageCustomFields(ExtraAllowModel):
    cache_breakpoint: CacheBreakpoint | None = None


class Message(ExtraAllowModel):
    role: Role
    content: StrictStr | list[MessageContentPart] | None = None
    custom_content: CustomContent | None = None
    custom_fields: MessageCustomFields | None = None
    name: StrictStr | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: StrictStr | None = None
    function_call: FunctionCall | None = None
    refusal: StrictStr | None = None
    reasoning_content: StrictStr | None = None

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


class Function(ExtraAllowModel):
    name: StrictStr
    strict: bool = False
    description: StrictStr | None = None
    parameters: dict | None = None


Temperature = Annotated[float, Field(ge=0, le=2)]
TopP = Annotated[float, Field(ge=0, le=1)]
N = Annotated[int, Field(ge=1, le=128)]
Stop = Annotated[list[StrictStr], Field(max_length=4)]
Penalty = Annotated[float, Field(ge=-2, le=2)]


class ToolCustomFields(ExtraAllowModel):
    cache_breakpoint: CacheBreakpoint | None = None


class Tool(ExtraAllowModel):
    type: Literal["function"]
    function: Function
    custom_fields: ToolCustomFields | None = None


class StaticFunction(ExtraAllowModel):
    name: str
    description: str | None = None
    configuration: dict[str, Any] | None = None


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
    description: StrictStr | None = None
    name: StrictStr
    schema_: dict[str, Any] = Field(..., alias="schema")
    strict: StrictBool | None = False

    if PYDANTIC_V2:

        @pyd2.model_serializer(mode="wrap")
        def serializer(
            self, nxt: pyd2.SerializerFunctionWrapHandler
        ) -> dict[str, Any]:
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
    include_usage: bool | None


ResponseFormat = (
    ResponseFormatText | ResponseFormatJsonObject | ResponseFormatJsonSchema
)


class PromptCacheOptions(ExtraAllowModel):
    mode: Literal["implicit", "explicit"] | None = None
    ttl: Literal["30m"] | StrictStr | None = None


class ReasoningEffort(str, Enum):
    NONE = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AzureChatCompletionRequest(ExtraAllowModel):
    model: StrictStr | None = None
    messages: list[Message]
    functions: list[Function] | None = None
    function_call: Literal["auto", "none"] | FunctionChoice | None = None
    tools: list[Tool | StaticTool] | None = None
    tool_choice: Literal["auto", "none", "required"] | ToolChoice | None = None
    stream: bool = False
    stream_options: StreamOptions | None = None
    temperature: Temperature | None = None
    top_p: TopP | None = None
    n: N | None = None
    stop: StrictStr | Stop | None = None
    max_tokens: PositiveInt | None = None
    max_completion_tokens: PositiveInt | None = None
    presence_penalty: Penalty | None = None
    frequency_penalty: Penalty | None = None
    logit_bias: Mapping[int, float] | None = None
    user: StrictStr | None = None
    seed: StrictInt | None = None
    logprobs: StrictBool | None = None
    top_logprobs: StrictInt | None = None
    reasoning_effort: ReasoningEffort | None = None
    response_format: ResponseFormat | None = None
    parallel_tool_calls: StrictBool | None = None
    prompt_cache_key: StrictStr | None = None
    prompt_cache_options: PromptCacheOptions | None = None


class ChatCompletionRequestCustomFields(ExtraAllowModel):
    configuration: dict[str, Any] | None = None
    cache_breakpoint: CacheBreakpoint | None = None


class ChatCompletionRequest(AzureChatCompletionRequest):
    max_prompt_tokens: PositiveInt | None = None
    custom_fields: ChatCompletionRequestCustomFields | None = None


class Request(ChatCompletionRequest, FromRequestDeploymentMixin):
    pass
