from aidial_sdk import (
    DIALApp,
    ChatCompletion,
    ChunkStream,
    ChatCompletionRequest,
)
import uvicorn
import asyncio


class ExampleApplication(ChatCompletion):
    async def chat_completion(
        self, stream: ChunkStream, request: ChatCompletionRequest
    ):
        for _ in range(request.n or 1):
            with stream.choice() as choice:
                choice.content("Some ")

                await asyncio.sleep(2)

                choice.content("Content")

                choice.attachment(
                    title="Some document title", data="Some document content..."
                )

                with choice.stage("Some stage") as stage:
                    stage.content("Some stage content")
                    stage.attachment(
                        title="Some document title for stage",
                        data="Some document content for stage...",
                    )

                choice.state([1, 2, 3, 4, 5])

        stream.usage(15, 23)

        stream.usage_per_model("gpt-4", 15, 23)
        stream.usage_per_model("gpt-5", 15, 23)


app = DIALApp()
app.add_chat_completion("app", ExampleApplication())

if __name__ == "__main__":
    uvicorn.run(app, port=5000)
