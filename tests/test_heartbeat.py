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

import itertools
import json
from typing import Generator, Iterator, List, Optional, Union

import pytest
from pydantic import BaseModel
from starlette.testclient import TestClient

from aidial_sdk import DIALApp
from tests.applications.idle import IdleApplication

ExpectedStream = List[Union[str, dict]]

BEAT = ": heartbeat"
DONE = "data: [DONE]"


def create_choice(
    *, finish_reason: Optional[str] = None, delta: Optional[dict] = {}
) -> dict:
    return {
        "choices": [
            {"index": 0, "finish_reason": finish_reason, "delta": delta}
        ],
        "usage": None,
        "id": "test_id",
        "created": 0,
        "object": "chat.completion.chunk",
    }


CHOICE_OPEN = create_choice(delta={"role": "assistant"})
CHOICE_CLOSE = create_choice(finish_reason="stop")


def content(content: str):
    return create_choice(delta={"content": content})


def match_sse_stream(expected: ExpectedStream, actual: Iterator[str]):

    def _add_newlines(
        stream: ExpectedStream,
    ) -> Generator[Union[str, dict], None, None]:
        for line in stream:
            yield line
            yield ""

    for expected_item, actual_line in itertools.zip_longest(
        _add_newlines(expected), actual
    ):
        if isinstance(expected_item, dict):
            assert actual_line[: len("data:")] == "data:"
            actual_line = actual_line[len("data:") :]
            actual_obj = json.loads(actual_line)
            assert actual_obj == expected_item
        else:
            assert actual_line == expected_item


class TestCase(BaseModel):
    __test__ = False

    intervals: List[float]
    heartbeat_timeout: Optional[float]
    expected: ExpectedStream


@pytest.mark.parametrize(
    "test_case",
    [
        TestCase(
            intervals=[2.0],
            heartbeat_timeout=1.5,
            expected=[
                BEAT,
                CHOICE_OPEN,
                content("1"),
                CHOICE_CLOSE,
                DONE,
            ],
        ),
        TestCase(
            intervals=[2.0, 2.0],
            heartbeat_timeout=1.5,
            expected=[
                BEAT,
                CHOICE_OPEN,
                content("1"),
                BEAT,
                content("2"),
                CHOICE_CLOSE,
                DONE,
            ],
        ),
        TestCase(
            intervals=[2.0] * 4,
            heartbeat_timeout=1.5,
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
                DONE,
            ],
        ),
        TestCase(
            intervals=[2.0],
            heartbeat_timeout=0.44,
            expected=[
                BEAT,
                BEAT,
                BEAT,
                BEAT,
                CHOICE_OPEN,
                content("1"),
                CHOICE_CLOSE,
                DONE,
            ],
        ),
        TestCase(
            intervals=[0.5] * 4,
            heartbeat_timeout=1.0,
            expected=[
                CHOICE_OPEN,
                content("1"),
                content("2"),
                content("3"),
                content("4"),
                CHOICE_CLOSE,
                DONE,
            ],
        ),
        TestCase(
            intervals=[2.0],
            heartbeat_timeout=None,
            expected=[
                CHOICE_OPEN,
                content("1"),
                CHOICE_CLOSE,
                DONE,
            ],
        ),
    ],
)
def test_heartbeat(test_case: TestCase):
    app_name = "app-name"

    app = DIALApp()
    app.add_chat_completion(
        app_name,
        IdleApplication(intervals=test_case.intervals),
        heartbeat_timeout=test_case.heartbeat_timeout,
    )

    client = TestClient(app)

    response = client.post(
        url=f"/openai/deployments/{app_name}/chat/completions",
        json={
            "messages": [{"role": "user", "content": "hello"}],
            "stream": True,
        },
        headers={"Api-Key": "TEST_API_KEY"},
    )

    match_sse_stream(test_case.expected, response.iter_lines())
