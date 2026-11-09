import gzip
import logging

import pytest
from starlette.testclient import TestClient
from starlette.types import Receive, Scope, Send

from aidial_sdk.utils._logging_middleware import LoggingMiddleware
from tests.applications.single_choice import SingleChoiceApplication
from tests.utils.client import create_app_client


def test_debug_logging_emits_each_stream_chunk_once(
    caplog: pytest.LogCaptureFixture,
):
    client = create_app_client(SingleChoiceApplication())

    with caplog.at_level(logging.DEBUG, logger="aidial_sdk"):
        response = client.post(
            "chat/completions",
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        )

    assert response.status_code == 200
    messages = [
        r.getMessage() for r in caplog.records if r.name == "aidial_sdk"
    ]
    events = [m.split("data: ", 1)[1] for m in messages if "data: " in m]
    assert events and len(events) == len(set(events))


_GZIPPED_BODY = gzip.compress(b"data: hi\n\n")


@pytest.mark.parametrize(
    "more_body, line",
    [
        (False, f"response: <gzip-encoded, {len(_GZIPPED_BODY)} bytes>"),
        (True, f"response chunk: <gzip-encoded, {len(_GZIPPED_BODY)} bytes>"),
    ],
)
def test_debug_logging_omits_a_compressed_body(
    caplog: pytest.LogCaptureFixture, more_body: bool, line: str
):
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-encoding", b"gzip")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": _GZIPPED_BODY,
                "more_body": more_body,
            }
        )
        if more_body:
            await send({"type": "http.response.body", "body": b""})

    with caplog.at_level(logging.DEBUG, logger="aidial_sdk"):
        TestClient(LoggingMiddleware(app)).get("/")

    assert [r.getMessage() for r in caplog.records] == [line]
