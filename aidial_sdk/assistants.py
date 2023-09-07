from abc import ABC, abstractmethod

from aidial_sdk.chat_completion.request import ChatCompletionRequest
from aidial_sdk.chunk_stream import ChunkStream


class ChatCompletion(ABC):
    @abstractmethod
    async def chat_completion(
        self, stream: ChunkStream, request: ChatCompletionRequest
    ):
        """Implement answer logic."""


class SimpleChatCompletion(ChatCompletion):
    @abstractmethod
    def content(self, request: ChatCompletionRequest) -> str:
        """Implement function that return content."""

    async def chat_completion(
        self, stream: ChunkStream, request: ChatCompletionRequest
    ):
        with stream.choice() as choice:
            choice.content(self.content(request))
