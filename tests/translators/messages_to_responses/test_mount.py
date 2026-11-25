import json
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
import respx
from fastapi import FastAPI, Request

from aidial_sdk.translators.messages_to_responses import mount_translator
from tests.translators.messages_to_chat_completions.helpers import (
    parse_anthropic_sse,
)
from tests.translators.messages_to_responses.helpers import (
    responses_body,
    text_item,
)

_CORE = "http://dial-core"
_CORE_PATH = "/openai/v1/responses"
_MESSAGES_URL = "/openaiResponses/anthropic/v1/messages"

# DIAL Core names the deployment in the header and its overrideName in the body
_MESSAGES_BODY = {
    "model": "gpt-5.5-2026-01-01",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "Hi"}],
}


@pytest.fixture
async def client(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("DIAL_URL", _CORE)
    async with httpx.AsyncClient() as core_client:

        async def get_client(_: Request) -> httpx.AsyncClient:
            return core_client

        app = FastAPI()
        mount_translator(app, get_client)
        async with httpx.AsyncClient(
            # httpx<0.28 types the ASGI messages as dict
            transport=httpx.ASGITransport(app),  # type: ignore
            base_url="http://test-app.com",
            headers={
                "api-key": "dummy-key",
                "x-dial-deployment-id": "gpt-5.5",
                "x-upstream-key": "secret",
            },
        ) as c:
            yield c


@pytest.fixture
def mock_core() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=_CORE) as mock:
        yield mock


async def test_block(
    client: httpx.AsyncClient, mock_core: respx.MockRouter
) -> None:
    route = mock_core.post(_CORE_PATH).respond(
        json=responses_body([text_item("Hello")])
    )

    response = await client.post(_MESSAGES_URL, json=_MESSAGES_BODY)

    assert response.json()["content"] == [{"type": "text", "text": "Hello"}]
    core_request = route.calls.last.request
    assert json.loads(core_request.content)["model"] == "gpt-5.5"
    assert core_request.headers["api-key"] == "dummy-key"
    assert "x-upstream-key" not in core_request.headers


async def test_stream(
    client: httpx.AsyncClient, mock_core: respx.MockRouter
) -> None:
    item = text_item("Hello")
    events: list[dict[str, Any]] = [
        {"type": "response.created", "response": responses_body([])},
        {
            "type": "response.output_text.delta",
            "output_index": 0,
            "content_index": 0,
            "delta": "Hello",
        },
        {"type": "response.output_item.done", "output_index": 0, "item": item},
        {"type": "response.completed", "response": responses_body([item])},
    ]
    # DIAL Core relays a heartbeat comment as a single line
    sse = ":ping\n" + "".join(f"data: {json.dumps(e)}\n\n" for e in events)
    mock_core.post(_CORE_PATH).respond(
        content=sse.encode(), content_type="text/event-stream"
    )

    response = await client.post(
        _MESSAGES_URL, json={**_MESSAGES_BODY, "stream": True}
    )

    assert [name for name, _ in parse_anthropic_sse(response.content)] == [
        "ping",
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]


async def test_core_error_is_translated(
    client: httpx.AsyncClient, mock_core: respx.MockRouter
) -> None:
    mock_core.post(_CORE_PATH).respond(
        status_code=429, json={"error": {"message": "Slow down"}}
    )

    response = await client.post(_MESSAGES_URL, json=_MESSAGES_BODY)

    assert response.status_code == 429
    assert response.json() == {
        "type": "error",
        "error": {"type": "rate_limit_error", "message": "Slow down"},
    }


async def test_unreachable_core_is_a_bad_gateway(
    client: httpx.AsyncClient, mock_core: respx.MockRouter
) -> None:
    mock_core.post(_CORE_PATH).mock(side_effect=httpx.ConnectError("refused"))

    response = await client.post(_MESSAGES_URL, json=_MESSAGES_BODY)

    assert response.status_code == 502
    assert response.json() == {
        "type": "error",
        "error": {"type": "api_error", "message": "Failed to reach DIAL Core"},
    }


async def test_unset_dial_url_is_an_internal_error(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DIAL_URL")

    response = await client.post(_MESSAGES_URL, json=_MESSAGES_BODY)

    assert response.status_code == 500
    assert response.json() == {
        "type": "error",
        "error": {"type": "api_error", "message": "Internal server error"},
    }


@pytest.mark.parametrize(
    "path",
    [
        "/openaiResponses/anthropic/v1/messages/count_tokens",
        "/openaiResponses/x",
    ],
    ids=["count-tokens", "unknown"],
)
async def test_other_paths_are_not_found(
    client: httpx.AsyncClient, path: str
) -> None:
    response = await client.post(path, json=_MESSAGES_BODY)

    assert response.status_code == 404
    assert response.json() == {
        "type": "error",
        "error": {
            "type": "not_found_error",
            "message": f"Unknown endpoint: {path}",
        },
    }
