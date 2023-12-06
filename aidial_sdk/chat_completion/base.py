from abc import ABC, abstractmethod

from aidial_sdk.chat_completion.request import (
    RateRequest,
    Request,
    TokenizeRequest,
    TokenizeResponse,
    TruncatePromptRequest,
    TruncatePromptResponse,
)
from aidial_sdk.chat_completion.response import Response


class ChatCompletion(ABC):
    @abstractmethod
    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        """Implement chat completion logic"""

    async def rate_response(self, request: RateRequest) -> None:
        """Implement rate response logic"""

    async def tokenize(self, request: TokenizeRequest) -> TokenizeResponse:
        """Implement tokenize logic"""
        raise NotImplementedError("tokenize method is not implemented")

    async def truncate_prompt(
        self, request: TruncatePromptRequest
    ) -> TruncatePromptResponse:
        """Implement truncate prompt logic"""
        raise NotImplementedError("truncate_prompt method is not implemented")
