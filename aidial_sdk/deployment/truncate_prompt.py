from typing import List, Literal, Union

from aidial_sdk.chat_completion.request import ChatCompletionRequest
from aidial_sdk.pydantic_v1 import BaseModel
from aidial_sdk.utils.pydantic import ExtraForbidModel


class TruncatePromptRequest(ExtraForbidModel):
    requests: List[ChatCompletionRequest]


class TruncatePromptSuccess(BaseModel):
    status: Literal["success"] = "success"
    discarded_messages: List[int]


class TruncatePromptError(BaseModel):
    status: Literal["error"] = "error"
    error: str


TruncatePromptResult = Union[TruncatePromptSuccess, TruncatePromptError]


class TruncatePromptResponse(BaseModel):
    responses: List[TruncatePromptResult]
    responses: List[TruncatePromptResult]
