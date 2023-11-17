from abc import ABC, abstractmethod

from aidial_sdk.chat_completion.request import RateRequest, Request
from aidial_sdk.chat_completion.response import Response


class ChatCompletion(ABC):
    @abstractmethod
    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        """Implement chat completion logic"""

    async def rate_response(self, request: RateRequest) -> None:
        """Implement rate response logic"""
