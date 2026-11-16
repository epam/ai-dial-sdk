"""
examples/travel_responses serves the two-turn tool loop in its README,
and every event and body conforms to openai's types on the way.
"""

import json
from typing import Any

import httpx
import openai
import pytest
from starlette.testclient import TestClient

from examples.travel_responses.app.main import app
from examples.travel_responses.app.model import POSTCARD_PNG, SIGHTS
from tests.responses.conftest import Transcript, check_http
from tests.utils import virtual_clock
from tests.utils.client import create_test_client

# The example paces its deltas with `asyncio.sleep`
pytestmark = pytest.mark.virtual_clock

QUESTION = "Plan a trip to Paris and Rome, and send me a postcard"

WEATHER_TOOL = {
    "type": "function",
    "name": "get_weather",
    "parameters": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
}
TOOLS = [WEATHER_TOOL, {"type": "web_search"}, {"type": "image_generation"}]

FORECASTS = {"Paris": "sunny, 24°C", "Rome": "cloudy, 19°C"}


def _post(stream: bool, **body: Any) -> Transcript:
    client = create_test_client(app, name="travel")
    http = client.post("responses", json={"stream": stream, **body})
    return check_http(http)


def _output(transcript: Transcript) -> list[dict]:
    assert transcript.http.status_code == 200
    assert transcript.body is not None
    return transcript.body["output"]


def _types(output: list[dict]) -> list[str]:
    return [item["type"] for item in output]


def _second_turn_input(question: str = QUESTION) -> list[dict]:
    """What the client sends back: the calls of turn 1 and their outputs."""
    items: list[dict] = [{"role": "user", "content": question}]
    for n, (city, forecast) in enumerate(FORECASTS.items()):
        call_id = f"call_{n}"
        items += [
            {
                "type": "function_call",
                "call_id": call_id,
                "name": "get_weather",
                "arguments": json.dumps({"city": city}),
            },
            {
                "type": "function_call_output",
                "call_id": call_id,
                "output": forecast,
            },
        ]
    return items


STREAM = pytest.mark.parametrize("stream", [False, True])


@STREAM
async def test_first_turn_calls_the_weather_tool_in_parallel(stream: bool):
    transcript = _post(stream, input=QUESTION, tools=TOOLS)

    output = _output(transcript)
    assert _types(output) == [
        "reasoning",
        "message",
        "function_call",
        "function_call",
    ]
    assert transcript.body is not None
    assert transcript.body["status"] == "completed"
    assert output[1]["phase"] == "commentary"
    assert [json.loads(call["arguments"]) for call in output[2:]] == [
        {"city": "Paris"},
        {"city": "Rome"},
    ]
    assert output[2]["call_id"] != output[3]["call_id"]

    if stream:
        # Both calls are open at once: their deltas alternate
        deltas = [
            event["output_index"]
            for event in transcript.stream
            if event["type"] == "response.function_call_arguments.delta"
        ]
        assert deltas == [2, 3, 2, 3]


async def test_first_turn_calls_one_at_a_time_without_parallel_tool_calls():
    output = _output(
        _post(False, input=QUESTION, tools=TOOLS, parallel_tool_calls=False)
    )
    calls = [item for item in output if item["type"] == "function_call"]
    assert [json.loads(call["arguments"]) for call in calls] == [
        {"city": "Paris"}
    ]


async def test_no_tool_call_with_tool_choice_none():
    output = _output(
        _post(False, input=QUESTION, tools=TOOLS, tool_choice="none")
    )
    assert "function_call" not in _types(output)
    assert output[-2]["phase"] == "final_answer"


@STREAM
async def test_second_turn_answers_with_citations_and_a_postcard(stream: bool):
    transcript = _post(stream, input=_second_turn_input(), tools=TOOLS)

    output = _output(transcript)
    assert _types(output) == [
        "reasoning",
        "web_search_call",
        "message",
        "image_generation_call",
    ]
    _, search, message, image = output

    assert search["status"] == "completed"
    assert search["action"]["query"] == "must-see sights in Paris and Rome"
    assert [source["url"] for source in search["action"]["sources"]] == [
        SIGHTS["Paris"].url,
        SIGHTS["Rome"].url,
    ]

    assert message["phase"] == "final_answer"
    assert message["status"] == "completed"
    [part] = message["content"]
    text = part["text"]
    for forecast in FORECASTS.values():
        assert forecast in text
    # Every citation spans exactly the title of the sight it cites
    citations = part["annotations"]
    assert [c["url"] for c in citations] == [
        SIGHTS["Paris"].url,
        SIGHTS["Rome"].url,
    ]
    for citation in citations:
        span = text[citation["start_index"] : citation["end_index"]]
        assert span == citation["title"]

    assert image["status"] == "completed"
    assert image["result"] == POSTCARD_PNG

    assert transcript.body is not None
    usage = transcript.body["usage"]
    assert usage["output_tokens_details"]["reasoning_tokens"] > 0
    assert (
        usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"]
    )

    if stream:
        partials = [
            event["partial_image_index"]
            for event in transcript.stream
            if event["type"] == "response.image_generation_call.partial_image"
        ]
        assert partials == [0, 1]


async def test_reasoning_summary_and_encrypted_content_only_when_asked():
    plain = _output(_post(False, input=QUESTION, tools=TOOLS))[0]
    assert plain["summary"] == []
    assert plain["encrypted_content"] is None
    assert plain["content"][0]["type"] == "reasoning_text"

    asked = _output(
        _post(
            False,
            input=QUESTION,
            tools=TOOLS,
            reasoning={"summary": "auto"},
            include=["reasoning.encrypted_content"],
        )
    )[0]
    assert asked["summary"] == [
        {"type": "summary_text", "text": "Checking the weather first."}
    ]
    assert asked["encrypted_content"]


@STREAM
async def test_max_output_tokens_stops_the_answer_short(stream: bool):
    transcript = _post(
        stream, input=_second_turn_input(), tools=TOOLS, max_output_tokens=5
    )

    output = _output(transcript)
    # Stopped before the postcard, too
    assert _types(output) == ["reasoning", "web_search_call", "message"]
    assert transcript.body is not None
    assert transcript.body["status"] == "incomplete"
    assert transcript.body["incomplete_details"] == {
        "reason": "max_output_tokens"
    }
    message = output[-1]
    assert message["status"] == "incomplete"
    assert len(message["content"][0]["text"].split()) == 5
    if stream:
        assert transcript.types[-1] == "response.incomplete"


@STREAM
async def test_refuses_to_book(stream: bool):
    output = _output(_post(stream, input="Book me a flight to Rome"))
    [message] = output
    [part] = message["content"]
    assert part["type"] == "refusal"
    assert part["refusal"].startswith("I can't book trips")


async def test_asks_for_a_city_it_knows():
    [message] = _output(_post(False, input="Where should I go?"))
    assert message["content"][0]["text"].startswith("I know Paris")


@STREAM
async def test_empty_question_is_an_http_error_without_a_stream(stream: bool):
    transcript = _post(stream, input=" ")
    assert transcript.http.status_code == 400
    assert transcript.stream == []
    assert transcript.http.json()["error"]["message"].startswith(
        "Ask about a trip"
    )


def _openai_client() -> openai.OpenAI:
    test_client = TestClient(
        app, backend_options=virtual_clock.backend_options()
    )

    def forward(request: httpx.Request) -> httpx.Response:
        response = test_client.request(
            request.method,
            str(request.url),
            headers=request.headers,
            content=request.read(),
        )
        # The client doesn't validate what it parses: `check_http` does
        check_http(response)
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            content=response.content,
        )

    return openai.OpenAI(
        base_url="http://testserver/openai/deployments/travel",
        api_key="unused",
        # DIAL hosting, not the protocol: DIAL core sends it to a deployment
        default_headers={"Api-Key": "TEST_API_KEY"},
        http_client=httpx.Client(transport=httpx.MockTransport(forward)),
        max_retries=0,
    )


@STREAM
async def test_openai_client_runs_the_tool_loop(stream: bool):
    """The README's loop, as an application would write it."""
    client = _openai_client()

    def create(input: Any) -> Any:
        if not stream:
            return client.responses.create(
                model="travel", input=input, tools=TOOLS
            )
        # Not `responses.stream`: its `Parsed*` items add a `parsed` field,
        # which isn't on the wire and isn't an input field either
        events = client.responses.create(
            model="travel", input=input, tools=TOOLS, stream=True
        )
        *_, completed = events
        assert completed.type == "response.completed"
        return completed.response

    history: list[Any] = [{"role": "user", "content": QUESTION}]
    first = create(history)
    calls = [item for item in first.output if item.type == "function_call"]
    assert len(calls) == 2

    # The client runs the tool and sends everything back: no state is kept
    history += first.output
    history += [
        {
            "type": "function_call_output",
            "call_id": call.call_id,
            "output": FORECASTS[json.loads(call.arguments)["city"]],
        }
        for call in calls
    ]
    second = create(history)

    assert second.status == "completed"
    assert [item.type for item in second.output] == [
        "reasoning",
        "web_search_call",
        "message",
        "image_generation_call",
    ]
    assert second.output_text == (
        "Your trip brief:\n"
        "- Paris: sunny, 24°C. Don't miss the Louvre.\n"
        "- Rome: cloudy, 19°C. Don't miss the Colosseum.\n"
    )
