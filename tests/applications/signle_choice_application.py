from aidial_sdk import (
    ChatCompletion,
    ChatCompletionRequest,
    ChatCompletionResponse,
)


class SingleChoiceApplication(ChatCompletion):
    async def chat_completion(
        self, request: ChatCompletionRequest, response: ChatCompletionResponse
    ) -> None:
        response.set_response_id("test_id")
        response.set_created(0)

        with response.create_single_choice() as choice:
            choice.append_content("123")
