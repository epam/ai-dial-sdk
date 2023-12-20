from enum import Enum
from typing import Any, Dict, List, Literal, Mapping, Optional, Union

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
    # OpenAI API doesn't strictly specify existence of the index field
    index: Optional[int]
    id: StrictStr
    type: Literal["function"]
    function: FunctionCall


class Role(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"
    TOOL = "tool"


class Message(ExtraForbidModel):
    role: Role
    content: Optional[StrictStr] = None
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
    type: Literal["function"]
    function: Function


class FunctionChoice(ExtraForbidModel):
    name: StrictStr


class ToolChoice(ExtraForbidModel):
    type: Literal["function"]
    function: FunctionChoice


class Request(ExtraForbidModel):
    model: Optional[StrictStr] = None
    messages: List[Message]
    functions: Optional[List[Function]] = None
    function_call: Optional[
        Union[Literal["auto", "none"], FunctionChoice]
    ] = None
    tools: Optional[List[Tool]] = None
    tool_choice: Optional[Union[Literal["auto", "none"], ToolChoice]] = None
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
