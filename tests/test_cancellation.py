import asyncio

import pytest

from aidial_sdk.chat_completion.request import Request as ChatCompletionRequest
from aidial_sdk.chat_completion.response import (
    Response as ChatCompletionResponse,
)
from aidial_sdk.pydantic_v1 import SecretStr
from aidial_sdk.utils.streaming import add_heartbeat


def create_chat_completion(status: asyncio.Future):

    async def _chat_completion(
        request: ChatCompletionRequest, response: ChatCompletionResponse
    ):
        try:
            for _ in range(10):
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            status.set_result(True)
            raise
        else:
            status.set_result(False)

    return _chat_completion


@pytest.mark.parametrize("with_heartbeat", [True, False])
async def test_cancellation(with_heartbeat: bool):

    request = ChatCompletionRequest(
        messages=[],
        api_key_secret=SecretStr("api-key"),
        deployment_id="test-app",
        headers={},
    )

    response = ChatCompletionResponse(request)

    cancellation_flag: asyncio.Future = asyncio.Future()
    chat_completion = create_chat_completion(cancellation_flag)

    async def _exhaust_stream(stream):
        async for _ in stream:
            pass

    try:
        stream = response._generate_stream(chat_completion)
        if with_heartbeat:
            stream = add_heartbeat(
                stream,
                heartbeat_interval=0.2,
                heartbeat_object=": heartbeat\n\n",
            )

        await asyncio.wait_for(_exhaust_stream(stream), timeout=2)
    except asyncio.TimeoutError:
        pass
    else:
        assert False, "Stream should have timed out"

    assert await cancellation_flag, "Stream should have been cancelled"
