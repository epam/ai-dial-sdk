import asyncio

import httpx
import pytest

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion.base import ChatCompletion
from tests.utils import virtual_clock
from tests.utils.uvicorn import run_uvicorn_in_thread


@pytest.fixture
def event_loop_policy(request: pytest.FixtureRequest):
    if request.node.get_closest_marker("virtual_clock") and (
        virtual_clock.is_enabled()
    ):
        return virtual_clock.VirtualClockEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()


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
