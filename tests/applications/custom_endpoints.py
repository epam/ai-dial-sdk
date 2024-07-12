import fastapi

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion import ChatCompletion, Request, Response
from aidial_sdk.deployment.tokenize import TokenizeRequest, TokenizeResponse


class NoopApplication(ChatCompletion):
    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        with response.create_single_choice():
            pass

    async def tokenize(self, request: TokenizeRequest) -> TokenizeResponse:
        return TokenizeResponse(outputs=[])


app = DIALApp().add_chat_completion("test-app1", NoopApplication())


@app.post("/openai/deployments/test-app1/tokenize")
async def tokenize(request: fastapi.Request):
    return {"result": "custom_tokenize_result"}


@app.post("/openai/deployments/test-app1/truncate_prompt")
async def truncate_prompt(request: fastapi.Request):
    return {"result": "custom_truncate_prompt_result"}


@app.post("/openai/deployments/test-app2/chat/completions")
async def chat_completion(request: fastapi.Request):
    return {"result": "custom_chat_completion_result"}
