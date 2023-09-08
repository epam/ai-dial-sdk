from abc import ABC, abstractmethod

from starlette.exceptions import HTTPException

from aidial_sdk.chat_completion.request import ChatCompletionRequest
from aidial_sdk.choice import SingleChoice
from aidial_sdk.chunk_stream import ChunkStream


class ChatCompletion(ABC):
    @abstractmethod
    async def chat_completion(
        self, stream: ChunkStream, request: ChatCompletionRequest
    ) -> None:
        """Implement answer logic."""


class SimpleChatCompletion(ChatCompletion):
    @abstractmethod
    def generate_content(self, request: ChatCompletionRequest) -> str:
        """Implement function that return content."""

    async def chat_completion(
        self, stream: ChunkStream, request: ChatCompletionRequest
    ):
        for _ in range(request.n or 1):
            with stream.choice() as choice:
                choice.content(self.generate_content(request))


class SingleChoiceChatCompletion(ChatCompletion):
    async def generate_choice(
        self,
        choice: SingleChoice,
        request: ChatCompletionRequest,
    ) -> None:
        """Implement function that generate choice."""

    async def chat_completion(
        self, stream: ChunkStream, request: ChatCompletionRequest
    ):
        if request.n and request.n > 1:
            raise HTTPException(
                400, f"{request.deployment_id} deployment doesn't support n > 1"
            )
            raise DIALException(400, "message", "type", "param", "code")

        with stream.single_choice() as choice:
            await self.generate_choice(choice, request)
