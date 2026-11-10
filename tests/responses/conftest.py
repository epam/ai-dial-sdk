import copy
import itertools
import json
import os
from collections import defaultdict
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Literal, get_args

import fastapi
import httpx2

# The installed pydantic, which openai's models are built on,
# regardless of the API the SDK is switched to by `PYDANTIC_V2`
import pydantic
import pytest
from openai.types.responses import Response as OpenAIResponse
from openai.types.responses import ResponseOutputItem, ResponseStreamEvent
from starlette.testclient import TestClient

from aidial_sdk import DIALApp
from aidial_sdk._pydantic import SecretStr
from aidial_sdk.deployment._headers import DIAL_DEPLOYMENT_ID
from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.exceptions import RuntimeServerError
from aidial_sdk.responses._context import _ResponseContext
from aidial_sdk.responses.base import ResponsesApplication
from aidial_sdk.responses.events import Event, _dump, to_sse_response
from aidial_sdk.responses.models import ResponseObject
from aidial_sdk.responses.request import DeploymentContext, Request
from aidial_sdk.responses.response import Response, _Producer
from aidial_sdk.utils.errors import RUNTIME_ERROR_MESSAGE

_INSTALLED_PYDANTIC_V2 = pydantic.VERSION.startswith("2.")

ValidationError = pydantic.ValidationError


@cache
def _type_adapter(type_: Any) -> Any:
    return pydantic.TypeAdapter(type_)


def _parse(type_: Any, raw: Any) -> Any:
    if _INSTALLED_PYDANTIC_V2:
        return _type_adapter(type_).validate_python(raw)

    from pydantic.v1 import parse_obj_as

    return parse_obj_as(type_, raw)


def _extra_fields(obj: Any, loc: tuple[Any, ...] = ()) -> list[tuple]:
    """The locations of fields an openai model received but doesn't declare."""
    if isinstance(obj, list | tuple):
        return [
            e for i, v in enumerate(obj) for e in _extra_fields(v, loc + (i,))
        ]
    if isinstance(obj, dict):
        return [e for k, v in obj.items() for e in _extra_fields(v, loc + (k,))]
    if not isinstance(obj, pydantic.BaseModel):
        return []

    if _INSTALLED_PYDANTIC_V2:
        fields = type(obj).model_fields
        extra = list(obj.model_extra or {})
    else:
        fields = obj.__fields__  # type: ignore
        extra = [name for name in obj.__dict__ if name not in fields]

    nested = [
        e
        for name in fields
        for e in _extra_fields(getattr(obj, name), loc + (name,))
    ]
    return [loc + (name,) for name in extra] + nested


def validate_as(type_: Any, raw: Any) -> None:
    """
    Parses `raw` as the openai `type_`. openai's models allow extra fields,
    so a stray or misspelled field is checked for separately.
    """
    extra = _extra_fields(_parse(type_, raw))
    assert not extra, f"Fields unknown to openai: {extra}"


def validate_event(raw: dict) -> None:
    """`raw` parses as an `openai` `ResponseStreamEvent`."""
    validate_as(ResponseStreamEvent, raw)


def validate_response(raw: dict) -> None:
    """`raw` parses as an `openai` `Response`."""
    validate_as(OpenAIResponse, raw)


def validate_stream(stream: list[dict]) -> None:
    """Each event conforms, and `sequence_number` runs from 0 without gaps."""
    for event in stream:
        validate_event(event)
    assert [e["sequence_number"] for e in stream] == list(range(len(stream)))


@contextmanager
def raises_runtime_error(caplog, reason: str) -> Iterator[None]:
    """
    A guard rail raises the generic `RuntimeServerError`;
    its reason only reaches the log.
    """
    with pytest.raises(RuntimeServerError) as exc_info:
        yield
    assert exc_info.value.message == RUNTIME_ERROR_MESSAGE
    assert reason in caplog.text


class _FixedIdContext(_ResponseContext):
    """Numbers the ids per prefix, so that transcripts are deterministic."""

    def __init__(
        self, *, stream: bool, response_object: ResponseObject | None = None
    ):
        if response_object is None:
            response_object = ResponseObject(id="", created_at=0, model="")
        response_object.id = "resp_1"
        response_object.created_at = 1700000000
        response_object.model = "m"
        super().__init__(response_object, stream=stream)
        self._counters = defaultdict(lambda: itertools.count(1))

    def new_id(self, prefix: str) -> str:
        return f"{prefix}_{next(self._counters[prefix])}"


def drain(ctx: _ResponseContext) -> list[Event]:
    """The events queued so far, each checked against openai."""
    drained = []
    while not ctx._queue.empty():
        drained.append(ctx._queue.get_nowait())
    for event in drained:
        validate_event(event)
    return drained


def _without(data: dict, key: str) -> dict:
    return {k: v for k, v in data.items() if k != key}


def accumulate_output(stream: list[Event]) -> list[dict]:
    """
    Rebuilds `output[]` the way a client would, from the `.added`
    events and the deltas. Each `.done` event must agree with what was
    rebuilt before it.
    """
    output: dict[int, Any] = {}
    delta_logprobs: dict[Any, list] = defaultdict(list)
    partial_images: dict[Any, int] = defaultdict(int)

    for event in stream:
        type_ = event["type"]
        index: Any = event.get("output_index")
        item: Any = output.get(index) if index is not None else None
        part: Any = None
        if "content_index" in event and type_ != "response.content_part.added":
            part = item["content"][event["content_index"]]
        if "summary_index" in event and not type_.endswith("part.added"):
            part = item["summary"][event["summary_index"]]

        if type_ == "response.output_item.added":
            output[index] = copy.deepcopy(event["item"])
        elif type_ == "response.output_item.done":
            for key in ("content", "summary", "arguments", "input"):
                if key in item:
                    assert item[key] == event["item"][key], key
            output[index] = event["item"]

        elif type_ == "response.content_part.added":
            item["content"] = item["content"] or []
            assert len(item["content"]) == event["content_index"]
            item["content"].append(copy.deepcopy(event["part"]))
        elif type_ == "response.content_part.done":
            # Delta logprobs carry no `bytes`: take them from the part
            assert _without(part, "logprobs") == _without(
                event["part"], "logprobs"
            )
            item["content"][event["content_index"]] = event["part"]
        elif type_ == "response.reasoning_summary_part.added":
            assert len(item["summary"]) == event["summary_index"]
            item["summary"].append(copy.deepcopy(event["part"]))
        elif type_ == "response.reasoning_summary_part.done":
            assert part == event["part"]

        elif type_ in (
            "response.output_text.delta",
            "response.reasoning_text.delta",
            "response.reasoning_summary_text.delta",
        ):
            part["text"] += event["delta"]
            delta_logprobs[index, event.get("content_index")] += event.get(
                "logprobs", []
            )
        elif type_ in (
            "response.output_text.done",
            "response.reasoning_text.done",
            "response.reasoning_summary_text.done",
        ):
            assert part["text"] == event["text"]
            assert delta_logprobs[
                index, event.get("content_index")
            ] == event.get("logprobs", [])
        elif type_ == "response.output_text.annotation.added":
            assert len(part["annotations"]) == event["annotation_index"]
            part["annotations"].append(event["annotation"])
        elif type_ == "response.refusal.delta":
            part["refusal"] += event["delta"]
        elif type_ == "response.refusal.done":
            assert part["refusal"] == event["refusal"]

        elif type_ == "response.function_call_arguments.delta":
            item["arguments"] += event["delta"]
        elif type_ == "response.function_call_arguments.done":
            assert item["arguments"] == event["arguments"]
            assert item["name"] == event["name"]
        elif type_ == "response.custom_tool_call_input.delta":
            item["input"] += event["delta"]
        elif type_ == "response.custom_tool_call_input.done":
            assert item["input"] == event["input"]

        elif type_ == "response.image_generation_call.partial_image":
            assert event["partial_image_index"] == partial_images[index]
            partial_images[index] += 1
        elif type_.startswith(
            ("response.web_search_call.", "response.image_generation_call.")
        ):
            assert item is not None
        else:
            raise AssertionError(f"Unexpected event: {type_}")

    assert sorted(output) == list(range(len(output)))
    return [output[index] for index in range(len(output))]


async def _frame(stream: list[Event]) -> str:
    async def events() -> AsyncIterator[Event | str]:
        for event in stream:
            yield event

    return "".join([chunk async for chunk in to_sse_response(events())])


async def run_builders(build: Callable[[_ResponseContext], Any]) -> str:
    """
    Runs `build` against a streaming and a block context and returns the
    SSE transcript. Every event is checked against openai, the output
    items too, and both modes against each other.
    """
    stream_ctx = _FixedIdContext(stream=True)
    build(stream_ctx)
    stream = drain(stream_ctx)

    block_ctx = _FixedIdContext(stream=False)
    build(block_ctx)
    block = _dump(block_ctx.response_object)

    validate_stream(stream)
    for item in block["output"]:
        validate_as(ResponseOutputItem, item)

    assert _dump(stream_ctx.response_object) == block
    assert accumulate_output(stream) == block["output"]

    return await _frame(stream)


def make_request(**body: Any) -> Request:
    return Request(
        **{"input": "Hi", **body},
        deployment=DeploymentContext(
            api_key_secret=SecretStr("key"),
            deployment_id="deployment",
            headers={},
            original_request=fastapi.Request({"type": "http"}),
        ),
    )


def make_response(*, stream: bool, **body: Any) -> Response:
    """
    A response with deterministic ids, see `_FixedIdContext`.
    The response object is the one `Response` built from the request.
    """
    response = Response(make_request(stream=stream, **body))
    response._ctx = _FixedIdContext(
        stream=stream, response_object=response._ctx.response_object
    )
    return response


LIFECYCLE_EVENTS = {
    "response.created",
    "response.in_progress",
    "response.completed",
    "response.incomplete",
    "response.failed",
}

TERMINAL_EVENTS = LIFECYCLE_EVENTS - {
    "response.created",
    "response.in_progress",
}


@dataclass
class Run:
    stream: list[Event]
    body: dict[str, Any]
    transcript: str
    exception: DIALException | None

    @property
    def types(self) -> list[str]:
        return [event["type"] for event in self.stream]


async def run_response(producer: _Producer, **body: Any) -> Run:
    """
    Runs `producer` as the handler of a streaming and a block response.
    Every event is checked against openai, the block body too, and both
    modes against each other.
    """
    stream_response = make_response(stream=True, **body)
    await stream_response._run_producer(producer)
    stream = drain(stream_response._ctx)

    block_response = make_response(stream=False, **body)
    await block_response._run_producer(producer)
    block = block_response._body
    assert block is not None
    assert repr(block_response._exception) == repr(stream_response._exception)

    validate_stream(stream)
    validate_response(block)

    created, in_progress, *_, terminal = stream
    assert created["type"] == "response.created"
    assert created["response"]["output"] == []
    assert in_progress["type"] == "response.in_progress"
    assert in_progress["response"] == created["response"]
    assert terminal["type"] in TERMINAL_EVENTS
    assert [e["type"] in TERMINAL_EVENTS for e in stream].count(True) == 1

    assert terminal["response"] == block
    item_events = [e for e in stream if "output_index" in e]
    assert accumulate_output(item_events) == block["output"]

    return Run(
        stream=stream,
        body=block,
        transcript=await _frame(stream),
        exception=stream_response._exception,
    )


_GOLDEN_DIR = Path(__file__).parent / "golden"


def assert_golden(name: str, transcript: str) -> None:
    """
    Compares with `golden/<name>.sse` byte for byte.
    `UPDATE_GOLDEN=1` rewrites the file instead: read it before committing.
    """
    path = _GOLDEN_DIR / f"{name}.sse"
    if os.environ.get("UPDATE_GOLDEN") == "1":
        path.write_text(transcript)
    assert path.read_text() == transcript


def parse_sse(body: str) -> tuple[list[dict], list[str]]:
    """The events of an SSE body, and its comments, i.e. heartbeats."""
    events, comments = [], []
    for frame in body.split("\n\n")[:-1]:
        if frame.startswith(":"):
            comments.append(frame)
            continue
        name, data = frame.split("\n")
        assert name.startswith("event: ") and data.startswith("data: ")
        event = json.loads(data[len("data: ") :])
        assert event["type"] == name[len("event: ") :]
        events.append(event)
    assert body.endswith("\n\n")
    return events, comments


@dataclass
class Transcript:
    http: httpx2.Response
    # The SSE events, or [] for a block response or an HTTP error
    stream: list[dict]
    comments: list[str]
    # The block body or the terminal event's snapshot, None for an HTTP error
    body: dict[str, Any] | None

    @property
    def types(self) -> list[str]:
        return [event["type"] for event in self.stream]


def check_http(http: httpx2.Response) -> Transcript:
    """
    Checks a response of the responses endpoint: every SSE event against
    openai, a block body too, the sequence numbers and the absence of
    `[DONE]`. An HTTP error is returned as is.
    """
    if http.status_code != 200:
        return Transcript(http=http, stream=[], comments=[], body=None)

    if not http.headers["content-type"].startswith("text/event-stream"):
        body = http.json()
        validate_response(body)
        return Transcript(http=http, stream=[], comments=[], body=body)

    assert "data: [DONE]" not in http.text.split("\n")
    stream, comments = parse_sse(http.text)
    validate_stream(stream)
    assert stream[0]["type"] == "response.created"
    assert stream[-1]["type"] in TERMINAL_EVENTS
    return Transcript(
        http=http,
        stream=stream,
        comments=comments,
        body=stream[-1]["response"],
    )


DEPLOYMENT = "test-deployment"

Handler = Callable[[Request, Response], Awaitable[None]]


class HandlerApp(ResponsesApplication):
    def __init__(self, handler: Handler):
        self._handler = handler

    async def create_response(
        self, request: Request, response: Response
    ) -> None:
        await self._handler(request, response)


Route = Literal["deployment", "v1"]

# The two routes `add_responses` registers: the deployment's own, and the
# shared one that finds the deployment by the header DIAL Core sends
_ROUTE_PATHS: dict[Route, tuple[str, dict[str, str]]] = {
    "deployment": (f"/openai/deployments/{DEPLOYMENT}/responses", {}),
    "v1": ("/openai/v1/responses", {DIAL_DEPLOYMENT_ID: DEPLOYMENT}),
}

ROUTES = pytest.mark.parametrize("route", get_args(Route))


def run_handler(
    handler: Handler,
    *,
    stream: bool,
    heartbeat_interval: float | None = None,
    route: Route = "deployment",
    **request: Any,
) -> Transcript:
    """
    Serves `handler` as a deployment and posts one request to it, on
    `route`, through `TestClient`. The response is checked by `check_http`.
    """
    app = DIALApp().add_responses(
        DEPLOYMENT, HandlerApp(handler), heartbeat_interval=heartbeat_interval
    )
    client = TestClient(app=app, headers={"api-key": "TEST_API_KEY"})
    path, headers = _ROUTE_PATHS[route]
    http = client.post(
        path,
        json={"input": "Hi", **request, "stream": stream},
        headers=headers,
    )
    return check_http(http)
