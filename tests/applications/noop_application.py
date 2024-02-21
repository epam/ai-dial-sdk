from aidial_sdk.chat_completion import ChatCompletion, Request, Response


class NoopApplication(ChatCompletion):
    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        with response.create_single_choice():
            pass
