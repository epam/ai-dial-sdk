from aidial_sdk.chat_completion import ChatCompletion, Request, Response
from tests.applications.broken_immediately import raise_exception


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

            raise_exception(request.messages[0].text())
