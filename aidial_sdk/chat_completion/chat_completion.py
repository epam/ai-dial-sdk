from abc import ABC, abstractmethod

from aidial_sdk.chat_completion.request import ChatCompletionRequest
from aidial_sdk.chat_completion.response import ChatCompletionResponse


class ChatCompletion(ABC):
    @abstractmethod
    async def chat_completion(
        self, request: ChatCompletionRequest, response: ChatCompletionResponse
    ) -> None:
        """Implement answer logic."""
