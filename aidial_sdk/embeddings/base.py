from abc import ABC, abstractmethod

from aidial_sdk.embeddings.request import Request
from aidial_sdk.embeddings.response import Response


class Embeddings(ABC):
    @abstractmethod
    async def embeddings(self, request: Request) -> Response:
        """Implement embeddings logic"""
