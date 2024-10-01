from fastapi import HTTPException as FastAPIException

from aidial_sdk import HTTPException as DIALException
from aidial_sdk.chat_completion import ChatCompletion, Request, Response
from tests.utils.request import get_message_text_content


def raise_exception(exception_type: str):
    if exception_type == "sdk_exception":
        raise DIALException("Test error", 503)
    elif exception_type == "fastapi_exception":
        raise FastAPIException(504, detail="Test detail")
    elif exception_type == "value_error_exception":
        raise ValueError("Test value error")
    elif exception_type == "zero_division_exception":
        return 1 / 0
    elif exception_type == "sdk_exception_with_display_message":
        raise DIALException("Test error", 503, display_message="I'm broken")
    else:
        raise DIALException("Unexpected error")


class BrokenApplication(ChatCompletion):
    """
    Application which breaks immediately after receiving a request.
    """

    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        raise_exception(get_message_text_content(request.messages[0]))
