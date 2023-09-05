from abc import ABC, abstractmethod
from dialsdk.chunk_stream import ChunkStream
from dialsdk.chat_completion.request import ChatCompletionRequest

class ChatCompletion(ABC):
    @abstractmethod
    async def chat_completion(self, stream: ChunkStream, request: ChatCompletionRequest):
        """Implement answer logic."""

class SimpleChatCompletion(ChatCompletion):
    @abstractmethod
    def content(self, request: ChatCompletionRequest) -> str:
        """Implement function that return content."""

    async def chat_completion(self, stream: ChunkStream, request: ChatCompletionRequest):
        with stream.stream() as stream:
            with stream.choice() as choice:
                choice.content(self.generate_content(request))
