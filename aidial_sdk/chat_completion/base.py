from abc import ABC, abstractmethod

from aidial_sdk.chat_completion.request import Request
from aidial_sdk.chat_completion.response import Response


class ChatCompletion(ABC):
    @abstractmethod
    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        """Implement chat completion logic"""
