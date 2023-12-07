from enum import Enum
from typing import Any, List, Mapping, Optional, Union

from aidial_sdk.deployment.parameters import DeploymentParametersMixin
from aidial_sdk.pydantic_v1 import (
    ConstrainedFloat,
    ConstrainedInt,
    ConstrainedList,
    PositiveInt,
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


class CustomContent(ExtraForbidModel):
    attachments: Optional[List[Attachment]] = None
    state: Optional[Any] = None


class Role(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"


class FunctionCall(ExtraForbidModel):
    name: str
    arguments: str


class Message(ExtraForbidModel):
    role: Role
    content: Optional[StrictStr] = None
    custom_content: Optional[CustomContent] = None
    name: Optional[StrictStr] = None
    function_call: Optional[FunctionCall] = None


class Addon(ExtraForbidModel):
    name: Optional[StrictStr] = None
    url: Optional[StrictStr] = None


class Function(ExtraForbidModel):
    name: StrictStr
    description: StrictStr
    parameters: StrictStr


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


class AzureChatCompletionRequest(ExtraForbidModel):
    messages: List[Message]
    functions: Optional[List[Function]] = None
    function_call: Optional[
        Union[StrictStr, Mapping[StrictStr, StrictStr]]
    ] = None
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


class ChatCompletionRequest(AzureChatCompletionRequest):
    model: Optional[StrictStr] = None
    addons: Optional[List[Addon]] = None
    max_prompt_tokens: Optional[PositiveInt] = None


class Request(ChatCompletionRequest, DeploymentParametersMixin):
    pass
