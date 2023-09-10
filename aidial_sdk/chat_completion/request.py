from typing import Any, List, Mapping, Optional, Union

from aidial_sdk.pydantic_v1 import (
    BaseModel,
    ConfigDict,
    ConstrainedFloat,
    ConstrainedInt,
    ConstrainedList,
    Extra,
    PositiveInt,
)

MODEL_CONFIG = ConfigDict(extra=Extra.forbid)


class Attachment(BaseModel):
    type: str = "text/markdown"
    title: Optional[str] = None
    data: Optional[str] = None
    url: Optional[str] = None
    reference_type: Optional[str] = None
    reference_url: Optional[str] = None

    model_config = MODEL_CONFIG


class CustomContent(BaseModel):
    attachments: Optional[List[Attachment]] = None
    state: Optional[Any] = None

    model_config = MODEL_CONFIG


class Message(BaseModel):
    role: str
    content: Optional[str] = None
    custom_content: Optional[CustomContent] = None
    name: Optional[str] = None
    function_call: Optional[str] = None

    model_config = MODEL_CONFIG


class Addon(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None

    model_config = MODEL_CONFIG


class Function(BaseModel):
    name: str
    description: str
    parameters: str

    model_config = MODEL_CONFIG


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


class ChatCompletionRequest(BaseModel):
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

    model_config = MODEL_CONFIG
