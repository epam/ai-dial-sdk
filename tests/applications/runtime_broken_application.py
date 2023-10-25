from aidial_sdk import HTTPException
from aidial_sdk.chat_completion import ChatCompletion, Request, Response


class RuntimeBrokenApplication(ChatCompletion):
    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        response.set_response_id("test_id")
        response.set_created(0)

        with response.create_single_choice() as choice:
            choice.append_content("Test content")
            await response.aflush()

            raise HTTPException("Test error", 503)
