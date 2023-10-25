from aidial_sdk import HTTPException
from aidial_sdk.chat_completion import ChatCompletion, Request, Response


class BrokenApplication(ChatCompletion):
    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        raise HTTPException("Test error", 503)
