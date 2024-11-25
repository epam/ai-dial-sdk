import httpx
from starlette.testclient import TestClient

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion.base import ChatCompletion


def create_app_client(
    chat_completion: ChatCompletion,
    *,
    name: str = "test_app",
    api_key: str | None = "TEST_API_KEY",
) -> httpx.Client:
    app = DIALApp().add_chat_completion(name, chat_completion)

    headers: dict[str, str] = {}
    if api_key:
        headers["Api-Key"] = api_key

    return TestClient(
        app=app,
        headers=headers,
        base_url=f"http://testserver/openai/deployments/{name}",
    )
