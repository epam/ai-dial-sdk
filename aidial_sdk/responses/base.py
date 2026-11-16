from abc import ABC, abstractmethod

from aidial_sdk.responses.request import Request
from aidial_sdk.responses.response import Response


class Responses(ABC):
    @abstractmethod
    async def create_response(
        self, request: Request, response: Response
    ) -> None:
        """Implement the Responses API logic"""
