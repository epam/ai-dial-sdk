from typing import List, Literal, Union

from aidial_sdk.chat_completion.request import ChatCompletionRequest
from aidial_sdk.pydantic_v1 import BaseModel
from aidial_sdk.utils.pydantic import ExtraForbidModel


class TokenizeRequest(ExtraForbidModel):
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
