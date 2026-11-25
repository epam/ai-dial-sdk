import asyncio
from typing import Any

import pytest
from starlette.testclient import TestClient

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion import ChatCompletion
from aidial_sdk.chat_completion import Request as ChatCompletionRequest
from aidial_sdk.chat_completion import Response as ChatCompletionResponse
from aidial_sdk.deployment._headers import DIAL_DEPLOYMENT_ID
from aidial_sdk.exceptions import RequestValidationError
from aidial_sdk.responses.base import Responses
from aidial_sdk.responses.request import Request
from aidial_sdk.responses.response import Response
from tests.responses.conftest import ROUTES, Route, check_http, run_handler

_NAME = "test-deployment"
_HEADERS = {"api-key": "TEST_API_KEY"}
_BODY = {"input": "Hi"}


class _Echo(Responses):
    async def create_response(
        self, request: Request, response: Response
    ) -> None:
        with response.create_message() as message:
            message.append_text(request.messages[-1].text())


def _client(app: DIALApp) -> TestClient:
    return TestClient(app=app, headers=_HEADERS)


@pytest.mark.parametrize(
    "path, headers",
    [
        (f"/openai/deployments/{_NAME}/responses", {}),
        ("/openai/v1/responses", {DIAL_DEPLOYMENT_ID: _NAME}),
    ],
)
def test_routes_answer(path: str, headers: dict[str, str]):
    client = _client(DIALApp().add_responses(_NAME, _Echo()))

    block = check_http(client.post(path, json=_BODY, headers=headers))
    assert block.http.status_code == 200
    assert block.http.headers["content-type"] == "application/json"
    assert block.body is not None
    assert block.body["model"] == _NAME
    assert block.body["output"][0]["content"][0]["text"] == "Hi"

    stream = check_http(
        client.post(path, json={**_BODY, "stream": True}, headers=headers)
    )
    assert stream.http.status_code == 200
    assert stream.http.headers["content-type"].startswith("text/event-stream")
    assert stream.comments == []
    assert stream.types[-1] == "response.completed"
    assert stream.body is not None
    assert stream.body["model"] == _NAME
    [message] = stream.body["output"]
    assert message["content"] == block.body["output"][0]["content"]


class _ModelSetter(Responses):
    def __init__(self, model: str | None):
        self._model = model

    async def create_response(
        self, request: Request, response: Response
    ) -> None:
        if self._model is not None:
            response.set_model(self._model)
        with response.create_message() as message:
            message.append_text("Hi")


_CLIENT_NAME = "client-deployment"


@pytest.mark.parametrize("stream", [True, False])
@pytest.mark.parametrize(
    "model, expected_model",
    [(None, _CLIENT_NAME), ("gpt-5.5", "gpt-5.5")],
    ids=["model-not-set", "model-set"],
)
def test_the_model_is_the_client_deployment_id(
    stream: bool, model: str | None, expected_model: str
):
    # DIAL Core sends the client-facing id, which the route's name may not be
    client = _client(DIALApp().add_responses(_NAME, _ModelSetter(model)))

    run = check_http(
        client.post(
            f"/openai/deployments/{_NAME}/responses",
            json={**_BODY, "stream": stream},
            headers={DIAL_DEPLOYMENT_ID: _CLIENT_NAME},
        )
    )

    assert run.http.status_code == 200
    assert run.body is not None
    assert run.body["model"] == expected_model
    for event in run.stream:
        if "response" in event:
            assert event["response"]["model"] == expected_model


def test_v1_route_dispatches_by_deployment():
    app = DIALApp().add_responses("a", _Echo()).add_responses("b", _Echo())
    client = _client(app)

    for name in ("a", "b"):
        run = check_http(
            client.post(
                "/openai/v1/responses",
                json=_BODY,
                headers={DIAL_DEPLOYMENT_ID: name},
            )
        )
        assert run.http.status_code == 200
        assert run.body is not None
        assert run.body["model"] == name

    response = client.post(
        "/openai/v1/responses",
        json=_BODY,
        headers={DIAL_DEPLOYMENT_ID: "c"},
    )
    assert response.status_code == 404


def test_no_other_endpoint():
    client = _client(DIALApp().add_responses(_NAME, _Echo()))

    for endpoint in ("chat/completions", "rate", "tokenize", "configuration"):
        response = client.post(
            f"/openai/deployments/{_NAME}/{endpoint}", json=_BODY
        )
        assert response.status_code in (404, 405), endpoint


class _Slow(Responses):
    async def create_response(
        self, request: Request, response: Response
    ) -> None:
        await asyncio.sleep(0.3)
        response.append_text("Hi")


@pytest.mark.parametrize("heartbeat_interval", [0.05, None])
def test_heartbeat(heartbeat_interval: float | None):
    app = DIALApp().add_responses(
        _NAME, _Slow(), heartbeat_interval=heartbeat_interval
    )

    run = check_http(
        _client(app).post(
            f"/openai/deployments/{_NAME}/responses",
            json={**_BODY, "stream": True},
        )
    )

    if heartbeat_interval:
        assert run.comments and set(run.comments) == {": heartbeat"}
        # The heartbeats came while the handler was idle, before any event
        assert run.http.text.startswith(": heartbeat\n\n")
    else:
        assert run.comments == []
    assert run.types[-1] == "response.completed"


class _BothProtocols(ChatCompletion, Responses):
    async def chat_completion(
        self, request: ChatCompletionRequest, response: ChatCompletionResponse
    ) -> None:
        with response.create_single_choice() as choice:
            choice.append_content("chat")

    async def create_response(
        self, request: Request, response: Response
    ) -> None:
        response.append_text("responses")


def test_one_deployment_serves_both_protocols():
    impl = _BothProtocols()
    app = DIALApp().add_chat_completion(_NAME, impl).add_responses(_NAME, impl)
    client = _client(app)

    chat = client.post(
        f"/openai/deployments/{_NAME}/chat/completions",
        json={"messages": [{"role": "user", "content": "Hi"}]},
    )
    assert chat.status_code == 200
    assert chat.json()["choices"][0]["message"]["content"] == "chat"

    for path, headers in [
        (f"/openai/deployments/{_NAME}/responses", {}),
        ("/openai/v1/responses", {DIAL_DEPLOYMENT_ID: _NAME}),
    ]:
        run = check_http(client.post(path, json=_BODY, headers=headers))
        assert run.http.status_code == 200
        assert run.body is not None
        assert run.body["output"][0]["content"][0]["text"] == "responses"


class _WithHeaders(Responses):
    async def create_response(
        self, request: Request, response: Response
    ) -> None:
        response.append_header("X-Upstream", "1")
        response.append_text("Hi")


def test_headers_reach_the_block_response():
    run = check_http(
        _client(DIALApp().add_responses(_NAME, _WithHeaders())).post(
            f"/openai/deployments/{_NAME}/responses", json=_BODY
        )
    )

    assert run.http.status_code == 200
    assert run.http.headers["X-Upstream"] == "1"


@ROUTES
@pytest.mark.parametrize(
    "field, value",
    [
        ("store", True),
        ("background", True),
        ("previous_response_id", "resp_1"),
        ("conversation", "conv_1"),
    ],
)
def test_stateful_field_is_rejected_before_the_handler(
    route: Route, field: str, value: Any
):
    """HTTP 422 with DIAL's error envelope, and the handler never runs."""
    called = False

    async def handler(request: Request, response: Response) -> None:
        nonlocal called
        called = True

    response = run_handler(
        handler, stream=False, route=route, **{field: value}
    ).http

    assert response.status_code == 422
    assert (
        response.json()
        == RequestValidationError(
            f"The request field {field!r} is not supported: "
            "the deployment doesn't store responses"
        ).json_error()
    )
    assert not called


@ROUTES
@pytest.mark.parametrize(
    "fields", [{}, {"store": False}], ids=["store-absent", "store-false"]
)
def test_stateless_request_is_answered(route: Route, fields: dict[str, Any]):
    async def handler(request: Request, response: Response) -> None:
        pass

    run = run_handler(handler, stream=False, route=route, **fields)

    assert run.http.status_code == 200
