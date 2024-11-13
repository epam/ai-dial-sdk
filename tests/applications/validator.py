from typing import Callable, Optional

from aidial_sdk.chat_completion import ChatCompletion, Request, Response

# It can be either function that raises AssertionError, or lambda that returns
# boolean, that will be used for assertion
RequestValidator = Callable[[Request], Optional[bool]]


class ValidatorApplication(ChatCompletion):
    def __init__(self, request_validator: RequestValidator):
        self.request_validator = request_validator

    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        result = self.request_validator(request)
        if result is not None:
            assert result
