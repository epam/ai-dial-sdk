"""
The goal of the SDK: openai's own client consumes a deployment built
with it, both ways, and the two agree.
"""

import itertools
from collections import defaultdict
from typing import Any

import httpx
import openai
import pytest
from starlette.testclient import TestClient

from aidial_sdk import DIALApp
from aidial_sdk.responses import Request, Response, _context
from tests.responses.conftest import DEPLOYMENT, HandlerApp, check_http


async def _handler(request: Request, response: Response) -> None:
    # Fixed, so that the two requests below answer alike
    response.set_response_id("resp_1").set_created(1700000000)

    with response.create_reasoning() as reasoning:
        reasoning.append_summary("Thinking")

    with response.create_message() as message:
        message.append_text("Hello, ").append_text("world")

    with response.create_function_call("get_weather", call_id="c1") as call:
        call.append_arguments('{"city":').append_arguments(' "Kyiv"}')

    response.set_usage(10, 20, reasoning_tokens=5)


# Added by openai's `Parsed*` types for structured outputs, not on the wire
_PARSED = {"parsed", "parsed_arguments"}


def _unparsed(data: Any) -> Any:
    if isinstance(data, list):
        return [_unparsed(v) for v in data]
    if isinstance(data, dict):
        return {k: _unparsed(v) for k, v in data.items() if k not in _PARSED}
    return data


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> openai.OpenAI:
    app = DIALApp().add_responses(DEPLOYMENT, HandlerApp(_handler))
    test_client = TestClient(app)

    def forward(request: httpx.Request) -> httpx.Response:
        # Item ids are numbered afresh per request, as `resp_1` is fixed
        counters = defaultdict(lambda: itertools.count(1))
        monkeypatch.setattr(
            _context, "new_id", lambda p: f"{p}_{next(counters[p])}"
        )
        response = test_client.request(
            request.method,
            str(request.url),
            headers=request.headers,
            content=request.read(),
        )
        # The client doesn't validate what it parses: the strict checks
        # run on its traffic here
        check_http(response)
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            content=response.content,
        )

    return openai.OpenAI(
        base_url=f"http://testserver/openai/deployments/{DEPLOYMENT}",
        api_key="unused",
        # DIAL hosting, not the protocol: DIAL core sends it to a deployment
        default_headers={"Api-Key": "TEST_API_KEY"},
        http_client=httpx.Client(transport=httpx.MockTransport(forward)),
        max_retries=0,
    )


def test_openai_client_streams_and_parses_alike(client: openai.OpenAI):
    """
    The client parses without validating, so its traffic goes through
    `check_http` too. What it adds is the client itself: its SSE decoding,
    and the accumulator behind `responses.stream`, which indexes into its
    snapshot with every event's `output_index` and `content_index` and
    rebuilds the text and the arguments from the deltas.
    """
    block = client.responses.create(model=DEPLOYMENT, input="Hi")

    stream = client.responses.create(model=DEPLOYMENT, input="Hi", stream=True)
    events = list(stream)

    text = arguments = None
    with client.responses.stream(model=DEPLOYMENT, input="Hi") as managed:
        for event in managed:
            # The text and the arguments so far, rebuilt from the deltas
            if event.type == "response.output_text.delta":
                text = event.snapshot
            elif event.type == "response.function_call_arguments.delta":
                arguments = event.snapshot
        # The payload of `response.completed`, not rebuilt from the deltas
        final = managed.get_final_response()

    assert events[-1].type == "response.completed"
    assert events[-1].response == block
    assert _unparsed(final.model_dump()) == block.model_dump()

    assert block.status == "completed"
    assert block.output_text == "Hello, world"
    reasoning, message, call = block.output
    assert reasoning.type == "reasoning"
    assert reasoning.summary[0].text == "Thinking"
    assert message.type == "message"
    assert call.type == "function_call"
    assert call.arguments == '{"city": "Kyiv"}'

    # What the client rebuilt from the deltas agrees with the block body
    assert text == block.output_text
    assert arguments == call.arguments
    assert block.usage is not None
    assert block.usage.total_tokens == 30
