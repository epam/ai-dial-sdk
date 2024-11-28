"""
Testing heartbeat feature.

Ideally we would like to see ReadTimeout exception thrown when the feature is disabled,
and not raised when it's enabled. To test it a test client supporting timeout is required.
None were found.

In absence of the timeout support we may try to measure elapsed time between
received chunks in the test itself.
This would require a test client which supports async streaming. None were found.

1. starlette.testclient.TestClient doesn't support timeouts and streaming:
    https://github.com/encode/starlette/issues/1108

2. httpx.ASGITransport doesn't support timeouts and streaming too:
    https://github.com/encode/httpx/issues/2186

3. async-asgi-testclient package has an alleged support of streaming and a basic catch-all timeout, but it didn't work for me for some reason.

The only other way is to actually spawn a test server in a dedicated process
as it's done in adapter-(vertexai|bedrock), but it has proven to be cumbersome:
https://github.com/epam/ai-dial-adapter-bedrock/blob/release-0.15/tests/conftest.py#L11-L15

So we resort here to testing purely the output of the application and check the presence of heartbeat messages.
"""

import asyncio
from contextlib import contextmanager
from typing import List, Optional, Union
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from aidial_sdk.application import DIALApp
from aidial_sdk.utils.streaming import add_heartbeat as original_add_heartbeat
from tests.applications.idle import IdleApplication
from tests.utils.chunks import check_sse_stream, create_single_choice_chunk
from tests.utils.client import create_test_client

BEAT = ": heartbeat"

ERROR = {
    "error": {
        "message": "Error during processing the request",
        "type": "runtime_error",
        "code": "500",
    }
}


CHOICE_OPEN = create_single_choice_chunk(delta={"role": "assistant"})
CHOICE_CLOSE = create_single_choice_chunk(finish_reason="stop")


def content(content: str):
    return create_single_choice_chunk(delta={"content": content})


@contextmanager
def mock_add_heartbeat(**extra_kwargs):
    with patch("aidial_sdk.application.add_heartbeat") as mock:

        def _updated_add_heartbeat(*args, **kwargs):
            return original_add_heartbeat(*args, **{**kwargs, **extra_kwargs})

        mock.side_effect = _updated_add_heartbeat
        yield mock


class TestCase(BaseModel):
    __test__ = False

    intervals: List[float]
    throw_exception: bool
    heartbeat_interval: Optional[float]
    expected: List[Union[str, dict]]


@pytest.mark.parametrize(
    "test_case",
    [
        TestCase(
            intervals=[2.0],
            heartbeat_interval=1.5,
            throw_exception=False,
            expected=[
                BEAT,
                CHOICE_OPEN,
                content("1"),
                CHOICE_CLOSE,
            ],
        ),
        TestCase(
            intervals=[2.0, 2.0],
            heartbeat_interval=1.5,
            throw_exception=False,
            expected=[
                BEAT,
                CHOICE_OPEN,
                content("1"),
                BEAT,
                content("2"),
                CHOICE_CLOSE,
            ],
        ),
        TestCase(
            intervals=[2.0] * 4,
            throw_exception=False,
            heartbeat_interval=1.5,
            expected=[
                BEAT,
                CHOICE_OPEN,
                content("1"),
                BEAT,
                content("2"),
                BEAT,
                content("3"),
                BEAT,
                content("4"),
                CHOICE_CLOSE,
            ],
        ),
        TestCase(
            intervals=[2.0],
            throw_exception=False,
            heartbeat_interval=0.44,
            expected=[
                BEAT,
                BEAT,
                BEAT,
                BEAT,
                CHOICE_OPEN,
                content("1"),
                CHOICE_CLOSE,
            ],
        ),
        TestCase(
            intervals=[0.5] * 4,
            throw_exception=False,
            heartbeat_interval=1.0,
            expected=[
                CHOICE_OPEN,
                content("1"),
                content("2"),
                content("3"),
                content("4"),
                CHOICE_CLOSE,
            ],
        ),
        TestCase(
            intervals=[2.0],
            throw_exception=False,
            heartbeat_interval=None,
            expected=[
                CHOICE_OPEN,
                content("1"),
                CHOICE_CLOSE,
            ],
        ),
        TestCase(
            intervals=[2.0],
            throw_exception=True,
            heartbeat_interval=1.5,
            expected=[
                BEAT,
                CHOICE_OPEN,
                content("1"),
                CHOICE_CLOSE,
                ERROR,
            ],
        ),
    ],
)
async def test_heartbeat(test_case: TestCase):
    beats: int = 0

    def inc_beat_counter():
        nonlocal beats
        beats += 1

    with mock_add_heartbeat(heartbeat_callback=inc_beat_counter):
        name = "test-deployment-name"
        app = DIALApp().add_chat_completion(
            name,
            IdleApplication(
                intervals=test_case.intervals,
                throw_exception=test_case.throw_exception,
            ),
            heartbeat_interval=test_case.heartbeat_interval,
        )

        client = create_test_client(app, name=name)

        response = client.post(
            url="chat/completions",
            json={
                "messages": [{"role": "user", "content": "hello"}],
                "stream": True,
            },
        )

        check_sse_stream(response.iter_lines(), test_case.expected)

        expected_beats = test_case.expected.count(BEAT)
        assert beats == expected_beats

        # Make sure the beats have stopped
        if test_case.heartbeat_interval is not None:
            await asyncio.sleep(test_case.heartbeat_interval * 2)
            assert beats == expected_beats
