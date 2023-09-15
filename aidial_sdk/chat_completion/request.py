from typing import Any, List, Literal, Mapping, Optional, Union

from aidial_sdk.pydantic_v1 import (
    BaseModel,
    ConstrainedFloat,
    ConstrainedInt,
    ConstrainedList,
    PositiveInt,
)


class ExtraForbidModel(BaseModel):
    class Config:
        extra = "forbid"


class Attachment(ExtraForbidModel):
    type: str = "text/markdown"
    title: Optional[str] = None
    data: Optional[str] = None
    url: Optional[str] = None
    reference_type: Optional[str] = None
    reference_url: Optional[str] = None


class CustomContent(ExtraForbidModel):
    attachments: Optional[List[Attachment]] = None
    state: Optional[Any] = None


class Message(ExtraForbidModel):
    role: Literal["system", "user", "assistant", "function"]
    content: Optional[str] = None
    custom_content: Optional[CustomContent] = None
    name: Optional[str] = None
    function_call: Optional[str] = None


class Addon(ExtraForbidModel):
    name: Optional[str] = None
    url: Optional[str] = None


class Function(ExtraForbidModel):
    name: str
    description: str
    parameters: str


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
    __args__ = tuple([str])


class Penalty(ConstrainedFloat):
    ge = -2
    le = 2


class ChatCompletionRequest(ExtraForbidModel):
    model: Optional[str] = None
    messages: List[Message]
    functions: Optional[List[Function]] = None
    function_call: Optional[Union[str, Mapping[str, str]]] = None
    addons: Optional[List[Addon]] = None
    stream: bool = False
    temperature: Optional[Temperature] = None
    top_p: Optional[TopP] = None
    n: Optional[N] = None
    stop: Optional[Union[str, Stop]] = None
    max_tokens: Optional[PositiveInt] = None
    presence_penalty: Optional[Penalty] = None
    frequency_penalty: Optional[Penalty] = None
    logit_bias: Optional[Mapping[int, float]] = None
    user: Optional[str] = None

    api_key: str
    jwt: Optional[str] = None
    deployment_id: str
    headers: Mapping[str, str]
