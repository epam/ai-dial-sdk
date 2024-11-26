from fastapi import HTTPException as FastAPIException

from aidial_sdk import HTTPException as DIALException
from aidial_sdk.chat_completion import ChatCompletion, Request, Response


def _raise_exception(exception_type: str):
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
    elif exception_type == "sdk_exception_with_headers":
        raise DIALException(
            "Too many requests", 429, headers={"Retry-After": "42"}
        )
    else:
        raise DIALException("Unexpected error")


class ImmediatelyBrokenApplication(ChatCompletion):
    """
    Application which breaks immediately after receiving a request.
    """

    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        _raise_exception(request.messages[0].text())


class RuntimeBrokenApplication(ChatCompletion):
    """
    Application which breaks after producing some output.
    """

    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        response.set_response_id("test_id")
        response.set_created(0)

        with response.create_single_choice() as choice:
            choice.append_content("Test content")
            await response.aflush()

            _raise_exception(request.messages[0].text())
