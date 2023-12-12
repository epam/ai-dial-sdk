from typing import Any, Dict, List, Literal, Mapping, Optional, Union

from typing_extensions import Annotated

from aidial_sdk.pydantic_v1 import (
    BaseModel,
    ConstrainedFloat,
    ConstrainedInt,
    ConstrainedList,
    Field,
    PositiveInt,
    StrictStr,
)


class ExtraForbidModel(BaseModel):
    class Config:
        extra = "forbid"


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


class FunctionCall(ExtraForbidModel):
    name: str
    arguments: str


class ToolCall(ExtraForbidModel):
    id: StrictStr
    type: Literal["function"]
    function: FunctionCall


class SystemMessage(ExtraForbidModel):
    role: Literal["system"]
    content: StrictStr
    name: Optional[StrictStr] = None


class UserMessage(ExtraForbidModel):
    role: Literal["user"]
    content: StrictStr
    name: Optional[StrictStr] = None


class AssistantMessage(ExtraForbidModel):
    role: Literal["assistant"]
    content: StrictStr
    name: Optional[StrictStr] = None
    tool_calls: Optional[List[ToolCall]] = None
    function_call: Optional[FunctionCall] = None


class ToolMessage(ExtraForbidModel):
    role: Literal["tool"]
    content: StrictStr
    tool_call_id: StrictStr


class FunctionMessage(ExtraForbidModel):
    role: Literal["function"]
    content: StrictStr
    name: StrictStr


Message = Annotated[
    Union[
        SystemMessage,
        UserMessage,
        AssistantMessage,
        ToolMessage,
        FunctionMessage,
    ],
    Field(discriminator="role"),
]


class Addon(ExtraForbidModel):
    name: Optional[StrictStr] = None
    url: Optional[StrictStr] = None


class Function(ExtraForbidModel):
    name: StrictStr
    description: Optional[StrictStr] = None
    parameters: Dict


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
    type: StrictStr
    function: Function


class Request(ExtraForbidModel):
    model: Optional[StrictStr] = None
    messages: List[Message]
    functions: Optional[List[Function]] = None
    function_call: Optional[
        Union[StrictStr, Mapping[StrictStr, StrictStr]]
    ] = None
    tools: Optional[Tool] = None
    tool_choice: Optional[
        Union[StrictStr, Mapping[StrictStr, StrictStr]]
    ] = None
    addons: Optional[List[Addon]] = None
    stream: bool = False
    temperature: Optional[Temperature] = None
    top_p: Optional[TopP] = None
    n: Optional[N] = None
    stop: Optional[Union[StrictStr, Stop]] = None
    max_tokens: Optional[PositiveInt] = None
    max_prompt_tokens: Optional[PositiveInt] = None
    presence_penalty: Optional[Penalty] = None
    frequency_penalty: Optional[Penalty] = None
    logit_bias: Optional[Mapping[int, float]] = None
    user: Optional[StrictStr] = None

    api_key: StrictStr
    jwt: Optional[StrictStr] = None
    deployment_id: StrictStr
    api_version: Optional[StrictStr] = None
    headers: Mapping[StrictStr, StrictStr]


class RateRequest(ExtraForbidModel):
    response_id: StrictStr = Field(None, alias="responseId")
    rate: bool = False
