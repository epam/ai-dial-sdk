import httpx
import pytest

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion.base import ChatCompletion
from tests.utils.uvicorn import run_uvicorn_in_thread


@pytest.fixture
async def test_http_client(chat_completion: ChatCompletion):
    app = DIALApp().add_chat_completion("app", chat_completion)

    async with (
        run_uvicorn_in_thread(app) as base_url,
        httpx.AsyncClient(
            base_url=f"{base_url}/openai/deployments/app",
            headers={"api-key": "test-api-key"},
        ) as client,
    ):
        yield client
