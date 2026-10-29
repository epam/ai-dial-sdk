import json
import logging
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import respx
from fastapi import Request
from httpx import ASGITransport

from aidial_sdk import DIALApp
from aidial_sdk.translators.messages_to_chat_completions import (
    ClientFactory,
    mount_translator,
)
from tests.translators.messages_to_chat_completions.helpers import (
    features_header,
    parse_anthropic_sse,
)

_MESSAGES_URL = "/openaiChatCompletions/anthropic/v1/messages"
_CORE = "http://dial-core"


_CORE_PATH = "/openai/v1/chat/completions"
_CORE_DEPLOYMENT_PATH = "/openai/deployments/gpt-5.5/chat/completions"

_RESPONSE_OBJECT: dict[str, object] = {
    "id": "chatcmpl_1",
    "object": "chat.completion",
    "model": "gpt-5.5",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "hi there"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 7, "completion_tokens": 3},
}

_MESSAGES_BODY: dict[str, object] = {
    "model": "gpt-5.5",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "hi"}],
}


@pytest.fixture
async def core_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as c:
        yield c


def _transport(get_client: ClientFactory[httpx.AsyncClient]) -> ASGITransport:
    app = DIALApp()
    mount_translator(app, get_client)
    # httpx<0.28 types the ASGI messages as dict
    return ASGITransport(app)  # type: ignore


@pytest.fixture
def transport(core_client: httpx.AsyncClient) -> ASGITransport:
    async def get_client(request: Request) -> httpx.AsyncClient:
        return core_client

    return _transport(get_client)


@pytest.fixture
async def client(
    monkeypatch: pytest.MonkeyPatch, transport: ASGITransport
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("DIAL_URL", _CORE)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test-app.com",
        headers={"api-key": "dummy-key"},
    ) as c:
        yield c


@pytest.fixture
def mock_core() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=_CORE, assert_all_called=False) as mock:
        yield mock


async def test_non_streaming_happy_path(
    client: httpx.AsyncClient, mock_core: respx.MockRouter
) -> None:
    mock_core.post(_CORE_PATH).respond(
        json=_RESPONSE_OBJECT, content_type="application/json"
    )
    response = await client.post(_MESSAGES_URL, json=_MESSAGES_BODY)

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "message"
    assert body["role"] == "assistant"
    assert body["content"][0]["text"] == "hi there"
    assert body["stop_reason"] == "end_turn"
    assert "stop_sequence" not in body
    assert body["usage"] == {
        "input_tokens": 7,
        "output_tokens": 3,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "output_tokens_details": {"thinking_tokens": 0},
    }


async def test_mount_with_client_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIAL_URL", _CORE)
    core_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=_RESPONSE_OBJECT)
        )
    )

    async with (
        core_client,
        httpx.AsyncClient(
            transport=_transport(core_client), base_url="http://test-app.com"
        ) as c,
    ):
        response = await c.post(_MESSAGES_URL, json=_MESSAGES_BODY)

    assert response.status_code == 200
    assert response.json()["content"][0]["text"] == "hi there"


async def test_request_shape_and_headers_not_leaked(
    client: httpx.AsyncClient, mock_core: respx.MockRouter
) -> None:
    route = mock_core.post(_CORE_PATH).respond(
        json=_RESPONSE_OBJECT, content_type="application/json"
    )
    await client.post(
        _MESSAGES_URL,
        json=_MESSAGES_BODY,
        headers={
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "oauth-2025-04-20",
        },
    )
    sent = route.calls.last.request
    sent_body = json.loads(sent.content)
    assert sent_body["model"] == "gpt-5.5"

    assert sent_body["max_completion_tokens"] == 100
    assert "max_tokens" not in sent_body

    assert "store" not in sent_body

    assert "anthropic-version" not in sent.headers
    assert "anthropic-beta" not in sent.headers
    assert sent.headers["api-key"] == "dummy-key"
    assert "authorization" not in sent.headers


async def test_cores_own_routing_headers_do_not_travel_on(
    client: httpx.AsyncClient, mock_core: respx.MockRouter
) -> None:
    route = mock_core.post(_CORE_PATH).respond(
        json=_RESPONSE_OBJECT, content_type="application/json"
    )
    await client.post(
        _MESSAGES_URL,
        json=_MESSAGES_BODY,
        headers={
            "x-upstream-endpoint": "https://provider.example/v1",
            "x-upstream-key": "provider-secret",
            "x-dial-override-name": "override",
            **features_header(),
        },
    )
    sent = route.calls.last.request
    for name in (
        "x-upstream-endpoint",
        "x-upstream-key",
        "x-dial-override-name",
        "x-dial-deployment-features",
    ):
        assert name not in sent.headers


@pytest.mark.parametrize(
    "inbound, forwarded",
    [
        ({"api-key": "core-key"}, "core-key"),
        ({"x-api-key": "client-key"}, None),
        ({"authorization": "Bearer jwt"}, None),
        ({"api-key": "core-key", "x-api-key": "client-key"}, "core-key"),
        ({"api-key": "core-key", "authorization": "Bearer jwt"}, "core-key"),
    ],
)
async def test_only_the_api_key_core_minted_travels_on(
    mock_core: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
    transport: ASGITransport,
    inbound: dict[str, str],
    forwarded: str | None,
) -> None:
    monkeypatch.setenv("DIAL_URL", _CORE)

    route = mock_core.post(_CORE_PATH).respond(
        json=_RESPONSE_OBJECT, content_type="application/json"
    )

    async with (
        httpx.AsyncClient(
            transport=transport,
            base_url="http://test-app.com",
        ) as bare,
    ):
        await bare.post(_MESSAGES_URL, json=_MESSAGES_BODY, headers=inbound)

    sent = route.calls.last.request
    assert sent.headers.get("api-key") == forwarded
    assert "x-api-key" not in sent.headers

    assert "authorization" not in sent.headers


@pytest.mark.parametrize(
    "headers",
    [
        {},
        features_header(
            temperature=False,
            reasoning_efforts=["low"],
            max_completion_tokens_supported=False,
        ),
        features_header(reasoning_efforts=[]),
        {"x-dial-deployment-features": "not json"},
        {"x-dial-deployment-features": "[]"},
    ],
    ids=[
        "absent",
        "unsupported-options",
        "empty-efforts",
        "invalid-json",
        "wrong-shape",
    ],
)
async def test_capabilities_do_not_filter_request_options(
    client: httpx.AsyncClient,
    mock_core: respx.MockRouter,
    headers: dict[str, str],
) -> None:
    route = mock_core.post(_CORE_PATH).respond(json=_RESPONSE_OBJECT)
    response = await client.post(
        _MESSAGES_URL,
        json={
            **_MESSAGES_BODY,
            "temperature": 0.5,
            "output_config": {"effort": "high"},
        },
        headers=headers,
    )
    assert response.status_code == 200
    assert len(mock_core.calls) == route.call_count == 1
    assert json.loads(route.calls.last.request.content) == {
        "model": "gpt-5.5",
        "messages": [{"role": "user", "content": "hi"}],
        "max_completion_tokens": 100,
        "temperature": 0.5,
        "reasoning_effort": "high",
        "stream": False,
    }


async def test_a_long_mcp_tool_name_round_trips(
    client: httpx.AsyncClient, mock_core: respx.MockRouter
) -> None:
    long_name = "mcp__" + "s" * 60 + "__do_the_thing"
    route = mock_core.post(_CORE_PATH).mock(
        side_effect=lambda request: httpx.Response(
            200,
            json={
                **_RESPONSE_OBJECT,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": json.loads(request.content)[
                                            "tools"
                                        ][0]["function"]["name"],
                                        "arguments": "{}",
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
            },
        )
    )
    response = await client.post(
        _MESSAGES_URL,
        json={
            **_MESSAGES_BODY,
            "tools": [{"name": long_name, "input_schema": {"type": "object"}}],
        },
    )

    assert response.status_code == 200
    sent_alias = json.loads(route.calls.last.request.content)["tools"][0][
        "function"
    ]["name"]
    assert sent_alias != long_name
    assert len(sent_alias) <= 64

    assert response.json()["content"][0]["name"] == long_name


async def test_a_long_mcp_tool_name_round_trips_while_streaming(
    client: httpx.AsyncClient, mock_core: respx.MockRouter
) -> None:
    long_name = "mcp__" + "s" * 60 + "__do_the_thing"

    def echo_the_alias(request: httpx.Request) -> httpx.Response:
        alias = json.loads(request.content)["tools"][0]["function"]["name"]
        frames = [
            {
                "id": "chatcmpl_1",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "gpt-5.5",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": alias,
                                        "arguments": "",
                                    },
                                }
                            ]
                        },
                        "finish_reason": None,
                    }
                ],
            },
            {
                "id": "chatcmpl_1",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "gpt-5.5",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "function": {"arguments": "{}"},
                                }
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
            },
        ]
        body = b"".join(
            b"data: " + json.dumps(frame).encode() + b"\n\n" for frame in frames
        )
        return httpx.Response(
            200,
            content=body + b"data: [DONE]\n\n",
            headers={"content-type": "text/event-stream"},
        )

    route = mock_core.post(_CORE_PATH).mock(side_effect=echo_the_alias)
    response = await client.post(
        _MESSAGES_URL,
        json={
            **_MESSAGES_BODY,
            "stream": True,
            "tools": [{"name": long_name, "input_schema": {"type": "object"}}],
        },
    )

    assert response.status_code == 200
    sent_alias = json.loads(route.calls.last.request.content)["tools"][0][
        "function"
    ]["name"]
    assert sent_alias != long_name
    assert len(sent_alias) <= 64

    assert f'"name":"{long_name}"' in response.text
    assert sent_alias not in response.text


async def test_streaming_happy_path(
    client: httpx.AsyncClient, mock_core: respx.MockRouter
) -> None:
    upstream_sse = (
        b'data: {"id": "chatcmpl_1", "model": "gpt-5.5", "choices": '
        b'[{"index": 0, "delta": {"role": "assistant", "content": "Hello"}, '
        b'"finish_reason": null}]}\n\n'
        b'data: {"id": "chatcmpl_1", "choices": [{"index": 0, "delta": {}, '
        b'"finish_reason": "stop"}]}\n\n'
        b'data: {"id": "chatcmpl_1", "choices": [], "usage": '
        b'{"prompt_tokens": 5, "completion_tokens": 2}}\n\n'
        b"data: [DONE]\n\n"
    )
    route = mock_core.post(_CORE_PATH).respond(
        content=upstream_sse, content_type="text/event-stream"
    )
    response = await client.post(
        _MESSAGES_URL, json={**_MESSAGES_BODY, "stream": True}
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    sent_body = json.loads(route.calls.last.request.content)
    assert sent_body["stream"] is True

    assert sent_body["stream_options"] == {"include_usage": True}
    text = response.text
    assert "event: message_start" in text
    assert "event: ping" not in text

    assert '"text":"Hello"' in text
    assert "event: message_stop" in text


async def test_x_dial_deployment_id_header_overrides_body_model(
    client: httpx.AsyncClient, mock_core: respx.MockRouter
) -> None:
    route = mock_core.post(_CORE_PATH).respond(
        json=_RESPONSE_OBJECT, content_type="application/json"
    )

    response = await client.post(
        _MESSAGES_URL,
        json=_MESSAGES_BODY,
        headers={"x-dial-deployment-id": "actual-deployment"},
    )

    assert response.status_code == 200
    assert route.called
    sent_body = json.loads(route.calls.last.request.content)
    assert sent_body["model"] == "actual-deployment"


async def test_connection_error_to_core_returns_502(
    client: httpx.AsyncClient, mock_core: respx.MockRouter
) -> None:
    mock_core.post(_CORE_PATH).mock(side_effect=httpx.ConnectError("refused"))
    response = await client.post(_MESSAGES_URL, json=_MESSAGES_BODY)
    assert response.status_code == 502
    body = response.json()
    assert body == {
        "type": "error",
        "error": {"type": "api_error", "message": "Failed to reach DIAL Core"},
    }


async def test_debug_logging_emits_request_and_response_lines(
    client: httpx.AsyncClient,
    mock_core: respx.MockRouter,
    caplog: pytest.LogCaptureFixture,
) -> None:
    mock_core.post(_CORE_PATH).respond(
        json=_RESPONSE_OBJECT, content_type="application/json"
    )
    with caplog.at_level(logging.DEBUG, logger="aidial_sdk"):
        response = await client.post(_MESSAGES_URL, json=_MESSAGES_BODY)

    assert response.status_code == 200
    messages = [
        r.getMessage() for r in caplog.records if r.name == "aidial_sdk"
    ]
    assert any(m.startswith("request: ") for m in messages)
    assert any(m.startswith("response: ") for m in messages)


async def test_debug_logging_emits_stream_chunk_lines(
    client: httpx.AsyncClient,
    mock_core: respx.MockRouter,
    caplog: pytest.LogCaptureFixture,
) -> None:
    upstream_sse = (
        b'data: {"id": "chatcmpl_1", "model": "gpt-5.5", "choices": '
        b'[{"index": 0, "delta": {"role": "assistant", "content": "Hi"}, '
        b'"finish_reason": "stop"}]}\n\n'
        b"data: [DONE]\n\n"
    )
    mock_core.post(_CORE_PATH).respond(
        content=upstream_sse, content_type="text/event-stream"
    )
    with caplog.at_level(logging.DEBUG, logger="aidial_sdk"):
        response = await client.post(
            _MESSAGES_URL, json={**_MESSAGES_BODY, "stream": True}
        )

    assert response.status_code == 200
    messages = [
        r.getMessage() for r in caplog.records if r.name == "aidial_sdk"
    ]
    assert any(m.startswith("response chunk: ") for m in messages)


async def test_missing_dial_url_returns_500(
    monkeypatch: pytest.MonkeyPatch, transport: ASGITransport
) -> None:
    monkeypatch.delenv("DIAL_URL", raising=False)

    async with (
        httpx.AsyncClient(
            transport=transport,
            base_url="http://test-app.com",
        ) as c,
    ):
        response = await c.post(_MESSAGES_URL, json=_MESSAGES_BODY)

    assert response.status_code == 500
    body = response.json()
    assert body["type"] == "error"
    assert body["error"]["type"] == "api_error"
    assert body["error"]["message"] == "Internal server error"


@pytest.mark.parametrize(
    "status, expected_type",
    [
        (422, "invalid_request_error"),
        (429, "rate_limit_error"),
        (529, "overloaded_error"),
        (418, "api_error"),
    ],
)
async def test_upstream_error_status_mapping(
    client: httpx.AsyncClient,
    mock_core: respx.MockRouter,
    status: int,
    expected_type: str,
) -> None:
    route = mock_core.post(_CORE_PATH).respond(
        status_code=status,
        json={"error": {"message": "upstream says no"}},
    )
    response = await client.post(_MESSAGES_URL, json=_MESSAGES_BODY)

    assert response.status_code == status
    body = response.json()
    assert body["error"]["type"] == expected_type
    assert body["error"]["message"] == "upstream says no"

    assert route.call_count == 1


async def test_pre_stream_error_returns_json_not_sse(
    client: httpx.AsyncClient, mock_core: respx.MockRouter
) -> None:
    mock_core.post(_CORE_PATH).respond(
        status_code=401, json={"error": {"message": "bad key"}}
    )
    response = await client.post(
        _MESSAGES_URL, json={**_MESSAGES_BODY, "stream": True}
    )
    assert response.status_code == 401
    assert "application/json" in response.headers["content-type"]
    assert response.json()["error"]["type"] == "authentication_error"


@pytest.mark.parametrize(
    "body",
    [
        {"output_config": {"effort": "extreme"}},
        {"messages": [{"role": "developer", "content": "hi"}]},
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "file", "file_id": "f1"},
                        }
                    ],
                }
            ]
        },
    ],
    ids=["effort", "role", "file-source"],
)
async def test_untranslatable_requests_return_400_without_calling_core(
    client: httpx.AsyncClient,
    mock_core: respx.MockRouter,
    body: dict[str, object],
) -> None:
    route = mock_core.post(_CORE_PATH).respond(json=_RESPONSE_OBJECT)
    response = await client.post(_MESSAGES_URL, json={**_MESSAGES_BODY, **body})
    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"
    assert not route.called


@pytest.mark.parametrize(
    "content", [b"not json", b"", b'{"model": "gpt-5.5"', b"\xff\xfe"]
)
async def test_invalid_json_returns_400_without_calling_core(
    client: httpx.AsyncClient, mock_core: respx.MockRouter, content: bytes
) -> None:
    route = mock_core.post(_CORE_PATH).respond(json=_RESPONSE_OBJECT)
    response = await client.post(
        _MESSAGES_URL,
        content=content,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["type"] == "invalid_request_error"
    assert error["message"].startswith("Request body is not valid JSON: ")
    assert not route.called


@pytest.mark.parametrize(
    "content",
    [b'{"foo": "boo"}', b"[]", b'{"model": "gpt-5.5", "messages": "hi"}'],
    ids=["no-fields", "not-an-object", "messages-not-a-list"],
)
async def test_a_valid_json_the_translator_cannot_read_is_not_a_client_error(
    client: httpx.AsyncClient, mock_core: respx.MockRouter, content: bytes
) -> None:
    route = mock_core.post(_CORE_PATH).respond(json=_RESPONSE_OBJECT)
    response = await client.post(
        _MESSAGES_URL,
        content=content,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 500
    assert response.json()["error"]["type"] == "api_error"
    assert not route.called


@pytest.mark.parametrize(
    "error, expected_type",
    [
        ({"type": "invalid_request_error"}, "invalid_request_error"),
        (
            {"type": "requests", "code": "rate_limit_exceeded"},
            "rate_limit_error",
        ),
        ({"type": "rate_limit_exceeded"}, "rate_limit_error"),
        ({"type": "runtime_error"}, "api_error"),
    ],
)
async def test_an_error_core_writes_into_the_stream_keeps_its_kind(
    client: httpx.AsyncClient,
    mock_core: respx.MockRouter,
    error: dict[str, object],
    expected_type: str,
) -> None:
    upstream_sse = (
        b'data: {"id": "chatcmpl_1", "model": "gpt-5.5", "choices": '
        b'[{"index": 0, "delta": {"content": "Hi"}, "finish_reason": null}]}'
        b"\n\n"
        + f"data: {json.dumps({'error': {'message': 'nope', **error}})}\n\n".encode()
    )
    mock_core.post(_CORE_PATH).respond(
        content=upstream_sse, content_type="text/event-stream"
    )
    response = await client.post(
        _MESSAGES_URL, json={**_MESSAGES_BODY, "stream": True}
    )
    events = parse_anthropic_sse(response.content)
    assert events[-1] == (
        "error",
        {"type": "error", "error": {"type": expected_type, "message": "nope"}},
    )


@pytest.mark.parametrize("sequences", [["STOP"], ["a", "b", "c", "d", "e"]])
async def test_stop_sequences_are_forwarded(
    client: httpx.AsyncClient,
    mock_core: respx.MockRouter,
    sequences: list[str],
) -> None:
    route = mock_core.post(_CORE_PATH).respond(json=_RESPONSE_OBJECT)
    response = await client.post(
        _MESSAGES_URL,
        json={**_MESSAGES_BODY, "model": "gpt-4o", "stop_sequences": sequences},
    )
    assert response.status_code == 200
    assert json.loads(route.calls.last.request.content)["stop"] == sequences


@pytest.mark.parametrize(
    "path",
    [
        "/anthropic/v1/messages/count_tokens",
        "/anthropic/v1/messages/batches",
        "/legacy/anthropic/v1/messages/count_tokens",
        "/legacy/anthropic/v1/messages/batches",
    ],
)
async def test_unsupported_endpoint_returns_anthropic_404(
    client: httpx.AsyncClient, path: str
) -> None:
    response = await client.post("/openaiChatCompletions" + path, json={})
    assert response.status_code == 404
    assert response.json() == {
        "type": "error",
        "error": {
            "type": "not_found_error",
            "message": f"Unknown endpoint: /openaiChatCompletions{path}",
        },
    }


@pytest.mark.parametrize("streaming", [False, True])
async def test_citation_configuration_is_sent_to_core(
    client: httpx.AsyncClient, mock_core: respx.MockRouter, streaming: bool
) -> None:
    request: dict[str, object] = {
        **_MESSAGES_BODY,
        "stream": streaming,
        "unused": "raw input",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "text",
                            "data": "doc",
                            "media_type": "text/plain",
                        },
                        "citations": {"enabled": True},
                    }
                ],
            }
        ],
    }
    route = mock_core.post(_CORE_PATH)
    if streaming:
        route.respond(
            content=b"data: [DONE]\n\n", content_type="text/event-stream"
        )
    else:
        route.respond(json=_RESPONSE_OBJECT)
    response = await client.post(_MESSAGES_URL, json=request)
    assert response.status_code == 200
    translated = json.loads(route.calls.last.request.content)
    assert translated["custom_fields"] == {
        "configuration": {"enable_citations": True}
    }
    assert translated["stream"] == streaming
    assert "unused" not in translated


async def test_only_whitelisted_headers_are_forwarded(
    client: httpx.AsyncClient, mock_core: respx.MockRouter
) -> None:
    route = mock_core.post(_CORE_PATH).respond(json=_RESPONSE_OBJECT)
    await client.post(
        _MESSAGES_URL,
        json=_MESSAGES_BODY,
        headers={
            "x-dial-cache-policy": "cache-priority",
            "x-upstream-id": "upstream-1",
            "x-conversation-id": "conversation-1",
            "x-claude-code-session-id": "session-1",
            "x-dial-extra": "value",
            "x-dial-cache-breakpoint-path": "inbound-path",
            "x-custom-header": "custom",
        },
    )
    sent = route.calls.last.request
    assert "api-version" not in sent.url.params
    assert sent.headers["api-key"] == "dummy-key"
    assert sent.headers["x-dial-cache-policy"] == "cache-priority"
    assert sent.headers["x-upstream-id"] == "upstream-1"
    assert "x-conversation-id" not in sent.headers
    assert "x-claude-code-session-id" not in sent.headers
    assert "x-dial-extra" not in sent.headers
    assert "x-dial-cache-breakpoint-path" not in sent.headers
    assert "x-custom-header" not in sent.headers
    assert "authorization" not in sent.headers


@pytest.mark.parametrize(
    "deployment", ["GPT-5.5", "gpt-5.5", "gpt-4o", "foobar"]
)
@pytest.mark.parametrize("streaming", [False, True])
async def test_stop_forwarding_is_independent_of_deployment_name(
    client: httpx.AsyncClient,
    mock_core: respx.MockRouter,
    deployment: str,
    streaming: bool,
) -> None:
    upstream = {
        **_RESPONSE_OBJECT,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "before STOP after",
                },
                "finish_reason": "stop",
            }
        ],
    }
    route = mock_core.post(_CORE_PATH)
    if streaming:
        chunk = {
            "id": "chatcmpl_1",
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": "before STOP after"},
                    "finish_reason": "stop",
                }
            ],
        }
        route.respond(
            content=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n",
            content_type="text/event-stream",
        )
    else:
        route.respond(json=upstream)
    response = await client.post(
        _MESSAGES_URL,
        json={
            **_MESSAGES_BODY,
            "stream": streaming,
            "stop_sequences": ["STOP"],
        },
        headers={"x-dial-deployment-id": deployment},
    )
    assert response.status_code == 200
    sent_body = json.loads(route.calls.last.request.content)
    assert sent_body["model"] == deployment
    assert sent_body["stop"] == ["STOP"]
    if streaming:
        events = parse_anthropic_sse(response.content)
        assert any(
            data.get("delta", {}).get("text") == "before STOP after"
            for _, data in events
        )
        assert (
            next(data for name, data in events if name == "message_delta")[
                "delta"
            ]["stop_sequence"]
            is None
        )
    else:
        assert "stop_sequence" not in response.json()
        assert response.json()["content"][0]["text"] == "before STOP after"


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize(
    "usage, cache_write",
    [
        ({}, 0),
        ({"prompt_tokens": None, "completion_tokens": None}, 0),
        (
            {
                "prompt_tokens": None,
                "completion_tokens": None,
                "prompt_tokens_details": {
                    "cached_tokens": None,
                    "cache_write_tokens": None,
                },
            },
            0,
        ),
    ],
)
async def test_missing_and_null_upstream_usage_counters(
    client: httpx.AsyncClient,
    mock_core: respx.MockRouter,
    streaming: bool,
    usage: dict[str, object],
    cache_write: int,
) -> None:
    upstream: dict[str, object] = {**_RESPONSE_OBJECT, "usage": usage}
    route = mock_core.post(_CORE_PATH)
    if streaming:
        route.respond(
            content=f"data: {json.dumps({'id': 'chatcmpl_1', 'choices': [], 'usage': usage})}\n\ndata: [DONE]\n\n",
            content_type="text/event-stream",
        )
    else:
        route.respond(json=upstream)
    response = await client.post(
        _MESSAGES_URL, json={**_MESSAGES_BODY, "stream": streaming}
    )
    assert response.status_code == 200
    if streaming:
        counters = next(
            event["usage"]
            for name, event in parse_anthropic_sse(response.content)
            if name == "message_delta"
        )
    else:
        counters = response.json()["usage"]
    assert counters["input_tokens"] == 0
    assert counters["output_tokens"] == 0
    assert counters["cache_creation_input_tokens"] == cache_write


async def test_invalid_upstream_response_returns_generic_server_error(
    client: httpx.AsyncClient,
    mock_core: respx.MockRouter,
    caplog: pytest.LogCaptureFixture,
) -> None:
    mock_core.post(_CORE_PATH).respond(json={**_RESPONSE_OBJECT, "id": 42})
    with caplog.at_level(logging.ERROR, logger="aidial_sdk"):
        response = await client.post(_MESSAGES_URL, json=_MESSAGES_BODY)
    assert response.status_code == 500
    assert response.json() == {
        "type": "error",
        "error": {"type": "api_error", "message": "Internal server error"},
    }
    assert any(record.exc_info is not None for record in caplog.records)


async def test_dropped_request_options_are_not_schema_validated(
    client: httpx.AsyncClient, mock_core: respx.MockRouter
) -> None:
    route = mock_core.post(_CORE_PATH).respond(json=_RESPONSE_OBJECT)
    response = await client.post(
        _MESSAGES_URL,
        json={
            **_MESSAGES_BODY,
            "thinking": {"type": "enabled"},
            "mcp_servers": [{"type": "future_server_type"}],
        },
    )
    assert response.status_code == 200
    translated = json.loads(route.calls.last.request.content)
    assert "mcp_servers" not in translated
    assert "thinking" not in translated
    assert "reasoning_effort" not in translated
    assert response.json()["type"] == "message"


_LEGACY_MESSAGES_URL = "/openaiChatCompletions/legacy/anthropic/v1/messages"
_LEGACY_CORE_PATH = "/openai/deployments/actual-deployment/chat/completions"


@pytest.mark.parametrize("streaming", [False, True])
async def test_legacy_endpoint_calls_the_deployment_path_of_core(
    client: httpx.AsyncClient,
    mock_core: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
    streaming: bool,
) -> None:
    monkeypatch.setenv("DIAL_API_VERSION", "custom-version")
    route = mock_core.post(_LEGACY_CORE_PATH)
    if streaming:
        route.respond(
            content=b'data: {"id": "chatcmpl_1", "choices": [{"index": 0, '
            b'"delta": {"content": "hi"}, "finish_reason": "stop"}]}\n\n'
            b"data: [DONE]\n\n",
            content_type="text/event-stream",
        )
    else:
        route.respond(json=_RESPONSE_OBJECT)

    response = await client.post(
        _LEGACY_MESSAGES_URL,
        json={**_MESSAGES_BODY, "stream": streaming},
        headers={"x-dial-deployment-id": "actual-deployment"},
    )

    assert response.status_code == 200
    sent = route.calls.last.request
    assert sent.url.params["api-version"] == "custom-version"
    assert json.loads(sent.content)["model"] == "actual-deployment"
    assert sent.headers["api-key"] == "dummy-key"
    if streaming:
        assert '"text":"hi"' in response.text
    else:
        assert response.json()["content"][0]["text"] == "hi there"


async def test_legacy_endpoint_defaults_the_api_version_and_the_body_model(
    client: httpx.AsyncClient, mock_core: respx.MockRouter
) -> None:
    route = mock_core.post(_CORE_DEPLOYMENT_PATH).respond(json=_RESPONSE_OBJECT)
    response = await client.post(_LEGACY_MESSAGES_URL, json=_MESSAGES_BODY)

    assert response.status_code == 200
    assert route.calls.last.request.url.params["api-version"] == (
        "2025-01-01-preview"
    )


async def test_legacy_endpoint_escapes_the_deployment_in_the_path(
    client: httpx.AsyncClient, mock_core: respx.MockRouter
) -> None:
    route = mock_core.post(
        url__regex=r"/openai/deployments/a%2Fb%3Fc/chat/completions"
    ).respond(json=_RESPONSE_OBJECT)
    response = await client.post(
        _LEGACY_MESSAGES_URL,
        json=_MESSAGES_BODY,
        headers={"x-dial-deployment-id": "a/b?c"},
    )

    assert response.status_code == 200
    assert route.called


async def test_the_v1_endpoint_sends_no_api_version(
    client: httpx.AsyncClient, mock_core: respx.MockRouter
) -> None:
    route = mock_core.post(_CORE_PATH).respond(json=_RESPONSE_OBJECT)
    await client.post(_MESSAGES_URL, json=_MESSAGES_BODY)
    assert "api-version" not in route.calls.last.request.url.params
