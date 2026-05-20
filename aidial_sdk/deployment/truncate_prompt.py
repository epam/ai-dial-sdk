from typing import Literal

from aidial_sdk._pydantic._compat import BaseModel
from aidial_sdk.chat_completion.request import ChatCompletionRequest
from aidial_sdk.deployment.from_request_mixin import FromRequestDeploymentMixin


class TruncatePromptRequest(FromRequestDeploymentMixin):
    inputs: list[ChatCompletionRequest]


class TruncatePromptSuccess(BaseModel):
    status: Literal["success"] = "success"
    discarded_messages: list[int]


class TruncatePromptError(BaseModel):
    status: Literal["error"] = "error"
    error: str


TruncatePromptResult = TruncatePromptSuccess | TruncatePromptError


class TruncatePromptResponse(BaseModel):
    outputs: list[TruncatePromptResult]
