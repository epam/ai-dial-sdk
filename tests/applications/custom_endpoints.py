from fastapi import Request
from fastapi.responses import JSONResponse

from aidial_sdk import DIALApp
from tests.applications.noop import NoopApplication

app = DIALApp().add_chat_completion("test_app1", NoopApplication())


@app.post("/openai/deployments/test_app1/tokenize")
async def tokenize(request: Request):
    return JSONResponse({"outputs": []})


@app.post("/openai/deployments/test_app2/chat/completions")
async def chat_completion(request: Request):
    return JSONResponse(
        {
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Test content"},
                }
            ]
        }
    )
