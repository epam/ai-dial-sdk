from typing import List, Literal, Union

from aidial_sdk.chat_completion.request import ChatCompletionRequest
from aidial_sdk.deployment.from_request_mixin import FromRequestDeploymentMixin
from aidial_sdk.pydantic_v1 import BaseModel


class TokenizeRequest(FromRequestDeploymentMixin):
    requests: List[Union[ChatCompletionRequest, str]]


class TokenizeSuccess(BaseModel):
    status: Literal["success"] = "success"
    token_count: int


class TokenizeError(BaseModel):
    status: Literal["error"] = "error"
    error: str


TokenizeResult = Union[TokenizeSuccess, TokenizeError]


class TokenizeResponse(BaseModel):
    responses: List[TokenizeResult]
