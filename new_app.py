import uvicorn

from aidial_sdk import (
    ChatCompletionRequest,
    DIALApp,
    SingleChoice,
    SingleChoiceChatCompletion,
)


class ExampleApplication(SingleChoiceChatCompletion):
    async def generate_choice(
        self,
        request: ChatCompletionRequest,
        choice: SingleChoice,
    ):
        # choice1 = stream.choice()
        # choice2 = stream.choice()

        choice.content("Content")
        choice.content("Content")

        await choice.aflush()

        # raise DIALException(message="some_text")

        choice.attachment(
            title="Some document title", data="Some document content..."
        )

        with choice.stage("Some stage #2") as stage:
            stage.content("Some stage content")
            stage.attachment(
                title="Some document title for stage",
                data="Some document content for stage...",
            )

        choice.state([1, 2, 3, 4, 5])

        choice.usage(15, 23)

        choice.usage_per_model("gpt-4", 15, 23)
        choice.usage_per_model("gpt-5", 15, 23)

        await choice.aflush()


app = DIALApp()
app.add_chat_completion("app", ExampleApplication())

if __name__ == "__main__":
    uvicorn.run(app, port=5000)
