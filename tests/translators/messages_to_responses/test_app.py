import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import anthropic
import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from aidial_sdk.deployment._headers import DIAL_DEPLOYMENT_ID
from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.translators.messages_to_responses import (
    expose_as_anthropic_messages,
)
from tests.translators.messages_to_chat_completions.auto_translation.helpers import (
    AnthropicClient,
)
from tests.translators.messages_to_responses.helpers import (
    responses_body,
    text_item,
)

Reply = Callable[[dict[str, Any]], Response]


def _sse(events: list[dict[str, Any]], *, heartbeat: bool = False):
    async def _generate() -> AsyncIterator[bytes]:
        if heartbeat:
            yield b": ping\n\n"
        for event in events:
            yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode()

    return _generate()


_USAGE = {
    "input_tokens": 10,
    "input_tokens_details": {"cached_tokens": 4},
    "output_tokens": 5,
    "output_tokens_details": {"reasoning_tokens": 0},
    "total_tokens": 15,
}


def _text_events(text: str) -> list[dict[str, Any]]:
    item = text_item(text)
    return [
        {"type": "response.created", "response": responses_body([])},
        {
            "type": "response.output_text.delta",
            "output_index": 0,
            "content_index": 0,
            "delta": text,
        },
        {"type": "response.output_item.done", "output_index": 0, "item": item},
        {
            "type": "response.completed",
            "response": responses_body([item], usage=_USAGE),
        },
    ]


def replying(text: str, **headers: str) -> Reply:
    def _reply(body: dict[str, Any]) -> Response:
        if body["stream"]:
            return StreamingResponse(
                _sse(_text_events(text)),
                media_type="text/event-stream",
                headers=headers,
            )
        return JSONResponse(
            responses_body([text_item(text)], usage=_USAGE), headers=headers
        )

    return _reply


class ScriptedResponses:
    """A Responses API handler that records the requests it gets."""

    def __init__(self, reply: Reply) -> None:
        self.reply = reply
        self.requests: list[Request] = []
        self.bodies: list[dict[str, Any]] = []

    async def __call__(self, request: Request) -> Response:
        self.requests.append(request)
        self.bodies.append(await request.json())
        return self.reply(self.bodies[-1])


def create_app(handler: ScriptedResponses, **kwargs: Any) -> FastAPI:
    app = FastAPI()
    expose_as_anthropic_messages(app, **kwargs)(
        app.post("/openai/v1/responses")(handler)
    )
    return app


def _http_client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        # httpx<0.28 types the ASGI messages as dict
        transport=httpx.ASGITransport(app, raise_app_exceptions=False),  # type: ignore
        base_url="http://dial-app",
    )


def anthropic_client(
    app: FastAPI, base_url: str = "http://dial-app/anthropic"
) -> AnthropicClient:
    return AnthropicClient(
        base_url=base_url,
        api_key="-",
        max_retries=0,
        default_headers={DIAL_DEPLOYMENT_ID: "gpt-5.5"},
        http_client=_http_client(app),
    )


async def test_answers_the_anthropic_client(stream: bool) -> None:
    app = create_app(ScriptedResponses(replying("Hello")))

    message = await anthropic_client(app).final_message(stream=stream)

    assert message.model_dump(exclude_none=True) == {
        "id": "resp_1",
        "type": "message",
        "role": "assistant",
        "model": "gpt-5.5",
        "content": [{"type": "text", "text": "Hello"}],
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": 6,
            "output_tokens": 5,
            "cache_read_input_tokens": 4,
            "cache_creation_input_tokens": 0,
            "output_tokens_details": {"thinking_tokens": 0},
        },
    }


async def test_handler_gets_the_responses_request(stream: bool) -> None:
    handler = ScriptedResponses(replying("Hello"))

    await anthropic_client(create_app(handler)).final_message(stream=stream)

    assert handler.bodies == [
        {
            "model": "ignored",
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Hello"}],
                }
            ],
            "max_output_tokens": 100,
            "store": False,
            "include": ["reasoning.encrypted_content"],
            "stream": stream,
        }
    ]
    request = handler.requests[0]
    assert request.headers["content-length"] == str(len(await request.body()))
    assert request.headers[DIAL_DEPLOYMENT_ID] == "gpt-5.5"


async def test_responses_route_is_kept() -> None:
    handler = ScriptedResponses(replying("Hello"))

    response = await _http_client(create_app(handler)).post(
        "/openai/v1/responses", json={"input": "Hi", "stream": False}
    )

    assert response.json()["output"][0]["content"][0]["text"] == "Hello"
    assert handler.bodies == [{"input": "Hi", "stream": False}]


async def test_path_is_configurable() -> None:
    app = create_app(
        ScriptedResponses(replying("Hello")),
        path="/openaiResponses/anthropic/v1/messages",
    )
    client = anthropic_client(
        app, base_url="http://dial-app/openaiResponses/anthropic"
    )

    message = await client.final_message(stream=False)

    assert message.content[0].type == "text"


async def test_handler_headers_are_kept(stream: bool) -> None:
    app = create_app(ScriptedResponses(replying("Hello", **{"x-trace": "t1"})))

    headers = await anthropic_client(app).response_headers(stream=stream)

    assert headers["x-trace"] == "t1"
    assert headers["content-type"] == (
        "text/event-stream; charset=utf-8" if stream else "application/json"
    )


async def test_heartbeat_is_a_ping() -> None:
    def _reply(_: dict[str, Any]) -> Response:
        return StreamingResponse(
            _sse(_text_events("Hi"), heartbeat=True),
            media_type="text/event-stream",
        )

    app = create_app(ScriptedResponses(_reply))

    assert await anthropic_client(app).stream_event_names() == [
        "ping",
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]


async def test_handler_body_is_closed_when_the_translation_fails() -> None:
    closed = False

    async def _events() -> AsyncIterator[bytes]:
        nonlocal closed
        try:
            yield b"data: {not json\n\n"
            yield b"data: never read\n\n"
        finally:
            closed = True

    def _reply(_: dict[str, Any]) -> Response:
        return StreamingResponse(_events(), media_type="text/event-stream")

    app = create_app(ScriptedResponses(_reply))

    assert await anthropic_client(app).stream_event_names() == ["error"]
    assert closed


async def test_request_naming_no_deployment_doesnt_reach_the_handler() -> None:
    handler = ScriptedResponses(replying("Hello"))

    response = await _http_client(create_app(handler)).post(
        "/anthropic/v1/messages",
        json={
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "Hi"}],
        },
    )

    assert response.status_code == 500
    assert response.json() == {
        "type": "error",
        "error": {
            "type": "api_error",
            "message": "The request headers are missing X-DIAL-DEPLOYMENT-ID header.",
        },
    }
    assert handler.requests == []


async def test_invalid_json_is_rejected() -> None:
    app = create_app(ScriptedResponses(replying("Hello")))

    response = await _http_client(app).post(
        "/anthropic/v1/messages", content=b"{not json"
    )

    assert response.status_code == 400
    assert response.json() == {
        "type": "error",
        "error": {
            "type": "invalid_request_error",
            "message": "Request body is not valid JSON: "
            "Expecting property name enclosed in double quotes: "
            "line 1 column 2 (char 1)",
        },
    }


class TestHandlerErrors:
    @pytest.mark.parametrize(
        "status_code, error_type",
        [
            (400, "invalid_request_error"),
            (429, "rate_limit_error"),
            (503, "overloaded_error"),
        ],
        ids=["invalid-request", "rate-limit", "overloaded"],
    )
    async def test_error_response_is_translated(
        self, stream: bool, status_code: int, error_type: str
    ) -> None:
        def _reply(_: dict[str, Any]) -> Response:
            return JSONResponse(
                {"error": {"message": "It failed", "code": "x"}},
                status_code=status_code,
                headers={"retry-after": "5"},
            )

        app = create_app(ScriptedResponses(_reply))

        with pytest.raises(anthropic.APIStatusError) as e:
            await anthropic_client(app).final_message(stream=stream)

        assert e.value.status_code == status_code
        assert e.value.body == {
            "type": "error",
            "error": {"type": error_type, "message": "It failed"},
        }
        assert e.value.response.headers["retry-after"] == "5"

    async def test_error_body_that_isnt_json_is_the_message(self) -> None:
        def _reply(_: dict[str, Any]) -> Response:
            return Response(b"Bad gateway", status_code=502)

        app = create_app(ScriptedResponses(_reply))

        with pytest.raises(anthropic.APIStatusError) as e:
            await anthropic_client(app).final_message(stream=False)

        assert e.value.body == {
            "type": "error",
            "error": {"type": "api_error", "message": "Bad gateway"},
        }

    async def test_raised_exception_is_answered_by_the_app_handler(
        self,
    ) -> None:
        class UpstreamError(Exception):
            pass

        def _reply(_: dict[str, Any]) -> Response:
            raise UpstreamError("Slow down")

        app = create_app(ScriptedResponses(_reply))

        async def _handle(_: Request, e: Exception) -> Response:
            return JSONResponse({"error": {"message": str(e)}}, status_code=429)

        app.add_exception_handler(UpstreamError, _handle)

        with pytest.raises(anthropic.APIStatusError) as e:
            await anthropic_client(app).final_message(stream=False)

        assert e.value.status_code == 429
        assert e.value.body == {
            "type": "error",
            "error": {"type": "rate_limit_error", "message": "Slow down"},
        }

    @pytest.mark.parametrize(
        "error, status_code, error_type, message",
        [
            (
                DIALException("Not here", status_code=404),
                404,
                "not_found_error",
                "Not here",
            ),
            (RuntimeError("boom"), 500, "api_error", "Internal server error"),
        ],
        ids=["dial-exception", "unexpected"],
    )
    async def test_exception_without_an_app_handler(
        self, error: Exception, status_code: int, error_type: str, message: str
    ) -> None:
        def _reply(_: dict[str, Any]) -> Response:
            raise error

        app = create_app(ScriptedResponses(_reply))

        with pytest.raises(anthropic.APIStatusError) as e:
            await anthropic_client(app).final_message(stream=False)

        assert e.value.status_code == status_code
        assert e.value.body == {
            "type": "error",
            "error": {"type": error_type, "message": message},
        }
