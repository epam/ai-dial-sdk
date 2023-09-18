import uvicorn

from aidial_sdk import (
    ChatCompletion,
    ChatCompletionRequest,
    ChatCompletionResponse,
    DIALApp,
)
from aidial_sdk.chat_completion.enums import Status


class ExampleApplication(ChatCompletion):
    async def chat_completion(
        self, request: ChatCompletionRequest, response: ChatCompletionResponse
    ) -> None:
        response.set_created(123456)
        response.set_model("gpt-10")
        response.set_response_id("random")

        with response.create_single_choice() as choice:
            choice.append_content("123")
            choice.append_content("Content2")

            choice.add_attachment(
                title="Some document title", data="Some document content..."
            )

            stage = choice.create_stage()
            stage.open()
            stage.append_name("Some ")
            stage.append_name("stage #1")
            stage.append_content("12")
            stage.close(Status.FAILED)

            with choice.create_stage("Some stage #2") as stage:
                stage.append_content("Some stage content")
                stage.add_attachment(
                    title="Some document title for stage",
                    data="Some document content for stage...",
                )

            choice.append_state([1, 2, 3, 4, 5])

        response.set_usage(15, 23)
        response.add_usage_per_model("gpt-4", 15, 23)
        response.add_usage_per_model("gpt-5", 23, 15)


if __name__ == "__main__":
    app = DIALApp()
    app.add_chat_completion("app", ExampleApplication())

    uvicorn.run(app, port=5000)
