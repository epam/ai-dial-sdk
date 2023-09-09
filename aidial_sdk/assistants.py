from abc import ABC, abstractmethod

from aidial_sdk.chat_completion.choice import SingleChoice
from aidial_sdk.chat_completion.request import ChatCompletionRequest
from aidial_sdk.chat_completion.response import ChatCompletionResponse
from aidial_sdk.exceptions import HTTPException


class ChatCompletion(ABC):
    @abstractmethod
    async def chat_completion(
        self, request: ChatCompletionRequest, response: ChatCompletionResponse
    ) -> None:
        """Implement answer logic."""


class SingleChoiceChatCompletion(ChatCompletion):
    async def generate_choice(
        self,
        request: ChatCompletionRequest,
        choice: SingleChoice,
    ) -> None:
        """Implement function that generate choice."""

    async def chat_completion(
        self, request: ChatCompletionRequest, response: ChatCompletionResponse
    ):
        if request.n and request.n > 1:
            raise HTTPException(
                f"{request.deployment_id} deployment doesn't support n > 1",
                status_code=400,
            )

        with response.single_choice() as choice:
            await self.generate_choice(request, choice)
