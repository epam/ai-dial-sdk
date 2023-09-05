from aidial_sdk import DIALApp, ChatCompletion, ChunkStream, ChatCompletionRequest
import uvicorn


class ExampleApplication(ChatCompletion):
    def chat_completion(self, stream: ChunkStream, request: ChatCompletionRequest):
        with stream.stream() as stream:
            for _ in range(request.n):
                with stream.choice() as choice:
                    choice.content("Some ")
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

    async def async_chat_completion(
        self, stream: ChunkStream, request: ChatCompletionRequest
    ):
        async with stream.a_stream() as stream:
            for _ in range(request.n):
                async with stream.a_choice() as choice:
                    await choice.a_content("Some ")
                    await choice.a_content("Content")

                    await choice.a_attachment(
                        title="Some document title", data="Some document content..."
                    )

                    async with choice.a_stage("Some stage") as stage:
                        await stage.a_content("Some stage content")
                        await stage.a_attachment(
                            title="Some document title for stage",
                            data="Some document content for stage...",
                        )

                    await choice.a_state([1, 2, 3, 4, 5])

            await stream.a_usage(15, 23)


app = DIALApp()
app.add_chat_completion("app", ExampleApplication())

if __name__ == "__main__":
    uvicorn.run(app, port=5000)
