from abc import ABC, abstractmethod
from typing import Union

from aidial_sdk.chat_completion.request import Request
from aidial_sdk.chat_completion.response import Response
from aidial_sdk.deployment.configuration import (
    ConfigurationRequest,
    ConfigurationResponse,
)
from aidial_sdk.deployment.rate import RateRequest
from aidial_sdk.deployment.tokenize import TokenizeRequest, TokenizeResponse
from aidial_sdk.deployment.truncate_prompt import (
    TruncatePromptRequest,
    TruncatePromptResponse,
)


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
        raise NotImplementedError()

    async def truncate_prompt(
        self, request: TruncatePromptRequest
    ) -> TruncatePromptResponse:
        """Implement truncate prompt logic"""
        raise NotImplementedError()

    async def configuration(
        self, request: ConfigurationRequest
    ) -> Union[ConfigurationResponse, dict]:
        """Implement configuration logic"""
        raise NotImplementedError()
