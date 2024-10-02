from enum import Enum
from typing import Any, Dict, List, Literal, Mapping, Optional, Union

from aidial_sdk.chat_completion.enums import Status
from aidial_sdk.deployment.from_request_mixin import FromRequestDeploymentMixin
from aidial_sdk.pydantic_v1 import (
    ConstrainedFloat,
    ConstrainedInt,
    ConstrainedList,
    PositiveInt,
    StrictBool,
    StrictInt,
    StrictStr,
)
from aidial_sdk.utils.pydantic import ExtraForbidModel


class Attachment(ExtraForbidModel):
    type: Optional[StrictStr] = "text/markdown"
    title: Optional[StrictStr] = None
    data: Optional[StrictStr] = None
    url: Optional[StrictStr] = None
    reference_type: Optional[StrictStr] = None
    reference_url: Optional[StrictStr] = None


class Stage(ExtraForbidModel):
    name: StrictStr
    status: Status
    content: Optional[StrictStr] = None
    attachments: Optional[List[Attachment]] = None


class CustomContent(ExtraForbidModel):
    stages: Optional[List[Stage]] = None
    attachments: Optional[List[Attachment]] = None
    state: Optional[Any] = None


class FunctionCall(ExtraForbidModel):
    name: str
    arguments: str


class ToolCall(ExtraForbidModel):
    # OpenAI API doesn't strictly specify existence of the index field
    index: Optional[int]
    id: StrictStr
    type: Literal["function"]
    function: FunctionCall


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"
    TOOL = "tool"


class ImageURL(ExtraForbidModel):
    url: StrictStr
    detail: Optional[Literal["auto", "low", "high"]] = None


class MessageContentImagePart(ExtraForbidModel):
    type: Literal["image_url"]
    image_url: ImageURL


class MessageContentTextPart(ExtraForbidModel):
    type: Literal["text"]
    text: StrictStr


MessageContentPart = Union[MessageContentTextPart, MessageContentImagePart]


class Message(ExtraForbidModel):
    role: Role
    content: Optional[Union[StrictStr, List[MessageContentPart]]] = None
    custom_content: Optional[CustomContent] = None
    name: Optional[StrictStr] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[StrictStr] = None
    function_call: Optional[FunctionCall] = None


class Addon(ExtraForbidModel):
    name: Optional[StrictStr] = None
    url: Optional[StrictStr] = None


class Function(ExtraForbidModel):
    name: StrictStr
    description: Optional[StrictStr] = None
    parameters: Optional[Dict] = None


class Temperature(ConstrainedFloat):
    ge = 0
    le = 2


class TopP(ConstrainedFloat):
    ge = 0
    le = 1


class N(ConstrainedInt):
    ge = 1
    le = 128


class Stop(ConstrainedList):
    max_items: int = 4
    __args__ = tuple([StrictStr])


class Penalty(ConstrainedFloat):
    ge = -2
    le = 2


class Tool(ExtraForbidModel):
    type: Literal["function"]
    function: Function


class FunctionChoice(ExtraForbidModel):
    name: StrictStr


class ToolChoice(ExtraForbidModel):
    type: Literal["function"]
    function: FunctionChoice


class ResponseFormat(ExtraForbidModel):
    type: Literal["text", "json_object"]


class AzureChatCompletionRequest(ExtraForbidModel):
    model: Optional[StrictStr] = None
    messages: List[Message]
    functions: Optional[List[Function]] = None
    function_call: Optional[Union[Literal["auto", "none"], FunctionChoice]] = (
        None
    )
    tools: Optional[List[Tool]] = None
    tool_choice: Optional[Union[Literal["auto", "none"], ToolChoice]] = None
    stream: bool = False
    temperature: Optional[Temperature] = None
    top_p: Optional[TopP] = None
    n: Optional[N] = None
    stop: Optional[Union[StrictStr, Stop]] = None
    max_tokens: Optional[PositiveInt] = None
    presence_penalty: Optional[Penalty] = None
    frequency_penalty: Optional[Penalty] = None
    logit_bias: Optional[Mapping[int, float]] = None
    user: Optional[StrictStr] = None
    seed: Optional[StrictInt] = None
    logprobs: Optional[StrictBool] = None
    top_logprobs: Optional[StrictInt] = None
    response_format: Optional[ResponseFormat] = None


class ChatCompletionRequestCustomFields(ExtraForbidModel):
    configuration: Optional[Dict[str, Any]] = None


class ChatCompletionRequest(AzureChatCompletionRequest):
    addons: Optional[List[Addon]] = None
    max_prompt_tokens: Optional[PositiveInt] = None
    custom_fields: Optional[ChatCompletionRequestCustomFields] = None


class Request(ChatCompletionRequest, FromRequestDeploymentMixin):
    pass
