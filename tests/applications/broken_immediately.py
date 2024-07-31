from fastapi import HTTPException as FastapiHTTPException

from aidial_sdk import HTTPException
from aidial_sdk.chat_completion import ChatCompletion, Request, Response


def raise_exception(exception_type: str):
    if exception_type == "sdk_exception":
        raise HTTPException("Test error", 503)
    elif exception_type == "fastapi_exception":
        raise FastapiHTTPException(504, detail="Test detail")
    elif exception_type == "value_error_exception":
        raise ValueError("Test value error")
    elif exception_type == "zero_division_exception":
        return 1 / 0
    elif exception_type == "sdk_exception_with_display_message":
        raise HTTPException("Test error", 503, display_message="I'm broken")
    else:
        raise HTTPException("Unexpected error")


class BrokenApplication(ChatCompletion):
    """
    Application which breaks immediately after receiving a request.
    """

    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        raise_exception(request.messages[0].content or "")
