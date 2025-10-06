from typing import List, Literal, Union

from aidial_sdk._pydantic._compat import BaseModel
from aidial_sdk.chat_completion.request import ChatCompletionRequest
from aidial_sdk.deployment.from_request_mixin import FromRequestDeploymentMixin


class TokenizeInputRequest(BaseModel):
    type: Literal["request"] = "request"
    value: ChatCompletionRequest


class TokenizeInputString(BaseModel):
    type: Literal["string"] = "string"
    value: str


TokenizeInput = Union[TokenizeInputRequest, TokenizeInputString]


class TokenizeRequest(FromRequestDeploymentMixin):
    inputs: List[TokenizeInput]


class TokenizeSuccess(BaseModel):
    status: Literal["success"] = "success"
    token_count: int


class TokenizeError(BaseModel):
    status: Literal["error"] = "error"
    error: str


TokenizeOutput = Union[TokenizeSuccess, TokenizeError]


class TokenizeResponse(BaseModel):
    outputs: List[TokenizeOutput]
