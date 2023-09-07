from typing import Any, List, Mapping, Optional, Union

from pydantic import BaseModel, ConfigDict, confloat, conint, conlist

MODEL_CONFIG = ConfigDict(extra="forbid")


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


class ChatCompletionRequest(BaseModel):
    model: Optional[str] = None
    messages: List[Message]
    functions: Optional[List[Function]] = None
    function_call: Optional[Union[str, Mapping[str, str]]] = None
    addons: Optional[List[Addon]] = None
    stream: bool = False
    temperature: Optional[confloat(ge=0, le=2)] = None
    top_p: Optional[confloat(ge=0, le=1)] = None
    n: Optional[conint(ge=1, le=128)] = None
    stop: Optional[Union[str, conlist(str, max_length=4)]] = None
    max_tokens: Optional[conint(ge=1)] = None
    presence_penalty: Optional[confloat(ge=-2, le=2)] = None
    frequency_penalty: Optional[confloat(ge=-2, le=2)] = None
    logit_bias: Optional[Mapping[int, float]] = None
    user: Optional[str] = None

    api_key: str
    jwt: Optional[str]
    deployment_id: str

    model_config = MODEL_CONFIG
