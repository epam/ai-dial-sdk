import json
from typing import Any

import fastapi
import httpx
import openai
import pytest
from starlette.testclient import TestClient

from aidial_sdk._pydantic import ValidationError
from aidial_sdk._pydantic._compat import BaseModel
from aidial_sdk.application import DIALApp
from aidial_sdk.chat_completion.request import Message as ChatMessage
from aidial_sdk.exceptions import InvalidRequestError, RequestValidationError
from aidial_sdk.responses.enums import MessagePhase
from aidial_sdk.responses.request import (
    CustomToolCallItem,
    CustomToolCallOutputItem,
    FunctionCallItem,
    FunctionCallOutputItem,
    InputAudioPart,
    InputFilePart,
    InputImagePart,
    InputItem,
    InputMessage,
    InputRole,
    InputTextPart,
    ItemReference,
    OutputTextPart,
    RawItem,
    ReasoningInputItem,
    RefusalContentPart,
    Request,
    RequestContext,
    ResponsesRequest,
)
from aidial_sdk.responses.response import Response
from tests.responses.conftest import run_handler
from tests.utils.pydantic import model_parse


class _Items(BaseModel):
    """Parses a list the way `ResponsesRequest.input` will."""

    items: list[InputItem]


def _parse(*items: Any) -> list[Any]:
    return _Items(items=list(items)).items


_UNKNOWN_ITEMS: list[dict[str, Any]] = [
    {"type": "web_search_call", "id": "ws_1", "status": "completed"},
    {"type": "mcp_call", "id": "mcp_1", "name": "n", "arguments": "{}"},
    {"type": "a_type_from_the_future", "payload": {"nested": [1, None]}},
]


@pytest.mark.parametrize("item", _UNKNOWN_ITEMS)
def test_unknown_type_falls_through_to_raw_item(item: dict[str, Any]):
    [parsed] = _parse(item)

    assert isinstance(parsed, RawItem)
    assert parsed.type == item["type"]
    assert json.dumps(parsed.raw) == json.dumps(item)


@pytest.mark.parametrize("stream", [True, False])
def test_handler_runs_on_unknown_items(stream: bool):
    # An unknown type never fails the request
    received: list[Any] = []

    async def handler(request: Request, response: Response) -> None:
        received.extend(request.input_items)
        response.append_text(request.messages[-1].text())

    message = {"role": "user", "content": "Hi"}
    run = run_handler(handler, stream=stream, input=[*_UNKNOWN_ITEMS, message])

    assert run.http.status_code == 200
    assert run.body is not None
    assert run.body["output"][0]["content"][0]["text"] == "Hi"
    *raw_items, _ = received
    assert [type(item) for item in raw_items] == [RawItem] * 3
    assert [json.dumps(item.raw) for item in raw_items] == [
        json.dumps(item) for item in _UNKNOWN_ITEMS
    ]


def test_raw_item_id_is_a_property():
    with_id, without_id, non_str_id = _parse(
        {"type": "mcp_call", "id": "mcp_1"},
        {"type": "mcp_call"},
        {"type": "mcp_call", "id": 42},
    )

    assert isinstance(RawItem.__dict__["id"], property)
    assert with_id.id == "mcp_1"
    assert without_id.id is None
    assert non_str_id.id is None


def test_raw_item_with_a_raw_field_of_its_own():
    item = {"type": "a_type_from_the_future", "raw": "not a dict"}

    [parsed] = _parse(item)

    assert isinstance(parsed, RawItem)
    assert parsed.raw == item


@pytest.mark.parametrize(
    "item, model",
    [
        ({"type": "message", "role": "user", "content": "hi"}, InputMessage),
        ({"role": "user", "content": "hi"}, InputMessage),
        (
            {
                "type": "function_call",
                "call_id": "c",
                "name": "n",
                "arguments": "{}",
            },
            FunctionCallItem,
        ),
        (
            {"type": "function_call_output", "call_id": "c", "output": "o"},
            FunctionCallOutputItem,
        ),
        (
            {
                "type": "custom_tool_call",
                "call_id": "c",
                "name": "n",
                "input": "i",
            },
            CustomToolCallItem,
        ),
        (
            {"type": "custom_tool_call_output", "call_id": "c", "output": "o"},
            CustomToolCallOutputItem,
        ),
        (
            {"type": "reasoning", "id": "rs_1", "summary": []},
            ReasoningInputItem,
        ),
        ({"type": "item_reference", "id": "msg_1"}, ItemReference),
        ({"id": "msg_1"}, ItemReference),
    ],
)
def test_known_types_resolve_to_their_models(item: dict[str, Any], model: type):
    [parsed] = _parse(item)

    assert type(parsed) is model


@pytest.mark.parametrize(
    "item",
    [
        {"type": "function_call", "name": "n", "arguments": "{}"},
        {"type": "function_call_output", "output": "o"},
        {"type": "message", "role": "nobody", "content": "hi"},
        {"type": "reasoning", "summary": []},
        {"type": "input_text", "text": "orphan part"},
        # A legacy message with an `id` must not become an item reference
        {"role": "tool", "content": "x", "id": "msg_1"},
        {
            "role": "user",
            "content": [{"type": "input_text", "text": 5}],
            "id": "msg_1",
        },
    ],
)
def test_malformed_known_type_is_an_error_not_a_raw_item(
    item: dict[str, Any],
):
    with pytest.raises(ValidationError):
        _parse(item)


@pytest.mark.parametrize("item", [{"foo": "bar"}, {"type": 1}, "text", 7])
def test_item_without_a_usable_type_is_an_error(item: Any):
    with pytest.raises(ValidationError):
        _parse(item)


def test_legacy_message_has_no_type():
    [parsed] = _parse({"role": "developer", "content": "be brief"})

    assert isinstance(parsed, InputMessage)
    assert parsed.type == "message"
    assert parsed.role == InputRole.DEVELOPER
    assert parsed.content == "be brief"


def test_message_content_parts():
    [parsed] = _parse(
        {
            "type": "message",
            "role": "assistant",
            "id": "msg_1",
            "status": "completed",
            "content": [
                {"type": "input_text", "text": "t"},
                {"type": "input_image", "image_url": "u", "detail": "auto"},
                {"type": "input_file", "file_id": "f", "filename": "f.txt"},
                {
                    "type": "input_audio",
                    "input_audio": {"data": "d", "format": "wav"},
                },
                {"type": "output_text", "text": "o", "annotations": []},
                {"type": "refusal", "refusal": "no"},
                {"type": "a_part_from_the_future", "x": 1},
            ],
        }
    )

    assert isinstance(parsed, InputMessage)
    assert isinstance(parsed.content, list)
    assert [type(part) for part in parsed.content] == [
        InputTextPart,
        InputImagePart,
        InputFilePart,
        InputAudioPart,
        OutputTextPart,
        RefusalContentPart,
        RawItem,
    ]
    unknown = parsed.content[-1]
    assert isinstance(unknown, RawItem)
    assert unknown.raw == {"type": "a_part_from_the_future", "x": 1}


def test_extra_fields_are_preserved():
    [parsed] = _parse(
        {"type": "message", "role": "user", "content": "hi", "unknown": "x"}
    )

    assert parsed.model_dump(exclude_none=True)["unknown"] == "x"


def _message(content: Any) -> InputMessage:
    [parsed] = _parse({"role": "user", "content": content})
    assert isinstance(parsed, InputMessage)
    return parsed


def test_text_of_string_content():
    assert _message("hello").text() == "hello"
    assert _message("").text() == ""


def test_text_concatenates_input_and_output_text_parts():
    message = _message(
        [
            {"type": "input_text", "text": "a"},
            {"type": "input_image", "image_url": "u"},
            {"type": "output_text", "text": "b", "annotations": []},
            {"type": "refusal", "refusal": "no"},
            {"type": "a_part_from_the_future", "text": "ignored"},
            {"type": "input_text", "text": "c"},
        ]
    )

    assert message.text() == "abc"


@pytest.mark.parametrize(
    "content",
    [
        [],
        [{"type": "input_image", "image_url": "u"}],
        [{"type": "refusal", "refusal": "no"}],
        [{"type": "a_part_from_the_future", "text": "ignored"}],
    ],
)
def test_text_is_empty_when_there_are_no_text_parts(content: list[Any]):
    assert _message(content).text() == ""


@pytest.mark.parametrize(
    "content, expected",
    [
        ("text", "text"),
        ("", ""),
        ([], ""),
        ([{"type": "input_image", "image_url": "u"}], ""),
        ([{"type": "refusal", "refusal": "no"}], ""),
        ([{"type": "a_part_from_the_future", "text": "x"}], ""),
        (
            [
                {"type": "a_part_from_the_future"},
                {"type": "input_text", "text": "a"},
                {"type": "refusal", "refusal": "no"},
                {"type": "output_text", "text": "b"},
            ],
            "ab",
        ),
    ],
)
def test_text_never_raises(content: Any, expected: str):
    # Deliberately unlike `chat_completion.Message.text()`, which raises
    # on a list of parts. Don't "fix" it to match.
    message = _message(content)

    assert message.text() == expected


def test_text_differs_from_chat_completion_on_a_list_of_parts():
    parts = [{"type": "input_text", "text": "a"}]

    chat_message = model_parse(
        ChatMessage,
        {"role": "user", "content": [{"type": "text", "text": "a"}]},
    )
    with pytest.raises(InvalidRequestError):
        chat_message.text()

    assert _message(parts).text() == "a"


def test_images():
    message = _message(
        [
            {"type": "input_text", "text": "look"},
            {"type": "input_image", "image_url": "u1", "detail": "low"},
            {"type": "input_image", "file_id": "f2"},
        ]
    )

    images = message.images()

    assert [(i.image_url, i.file_id, i.detail) for i in images] == [
        ("u1", None, "low"),
        (None, "f2", None),
    ]
    assert _message("no parts").images() == []
    assert _message([{"type": "input_text", "text": "t"}]).images() == []


def _record(**params: Any) -> dict[str, Any]:
    """Returns the body `openai`'s client sends for `responses.create`."""
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={})

    client = openai.OpenAI(
        api_key="key",
        base_url="http://dial.test/openai/v1",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client.responses.create(**params)

    [body] = bodies
    return body


_FUNCTION = {
    "type": "function",
    "name": "get_weather",
    "description": "Weather",
    "parameters": {"type": "object", "properties": {}},
    "strict": True,
}

_FIXTURES: dict[str, dict[str, Any]] = {
    "string-input": {"model": "m", "input": "hi"},
    "sampling": {
        "model": "m",
        "input": "hi",
        "instructions": "be brief",
        "temperature": 0.5,
        "top_p": 0.9,
        "top_logprobs": 3,
        "max_output_tokens": 100,
        "truncation": "auto",
        "include": ["reasoning.encrypted_content"],
        "metadata": {"k": "v"},
        "user": "u",
        "prompt_cache_key": "pck",
        "safety_identifier": "sid",
        "parallel_tool_calls": False,
        "max_tool_calls": 2,
        "store": False,
    },
    "streaming": {
        "model": "m",
        "input": "hi",
        "stream": True,
        "stream_options": {"include_obfuscation": False},
    },
    "text-and-reasoning": {
        "model": "m",
        "input": "hi",
        "text": {
            "format": {
                "type": "json_schema",
                "name": "n",
                "schema": {"type": "object"},
                "strict": True,
            },
            "verbosity": "low",
        },
        "reasoning": {"effort": "high", "summary": "auto"},
    },
    "messages": {
        "model": "m",
        "input": [
            {"role": "developer", "content": "rules"},
            {"type": "message", "role": "user", "content": "plain"},
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "look"},
                    {
                        "type": "input_image",
                        "image_url": "https://a.b/i.png",
                        "detail": "low",
                    },
                    {"type": "input_file", "file_id": "file-1"},
                    {
                        "type": "input_file",
                        "filename": "f.txt",
                        "file_data": "ZGF0YQ==",
                    },
                ],
            },
            {
                "type": "message",
                "role": "assistant",
                "id": "msg_1",
                "status": "completed",
                "content": [
                    {"type": "output_text", "text": "hi", "annotations": []},
                    {"type": "refusal", "refusal": "no"},
                ],
            },
        ],
    },
    "tool-traffic": {
        "model": "m",
        "input": [
            {"role": "user", "content": "weather?"},
            {
                "type": "reasoning",
                "id": "rs_1",
                "summary": [{"type": "summary_text", "text": "thinking"}],
                "encrypted_content": "enc",
            },
            {
                "type": "function_call",
                "call_id": "call_1",
                "name": "get_weather",
                "arguments": "{}",
                "id": "fc_1",
            },
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": "sunny",
            },
            {
                "type": "custom_tool_call",
                "call_id": "call_2",
                "name": "patch",
                "input": "diff",
            },
            {
                "type": "custom_tool_call_output",
                "call_id": "call_2",
                "output": "applied",
            },
            {"type": "item_reference", "id": "msg_0"},
        ],
    },
    "tools": {
        "model": "m",
        "input": "hi",
        "tools": [
            _FUNCTION,
            {"type": "custom", "name": "patch", "format": {"type": "text"}},
            {"type": "web_search", "search_context_size": "low"},
            {
                "type": "mcp",
                "server_label": "s",
                "server_url": "https://a.b/mcp",
                "require_approval": "never",
            },
        ],
        "tool_choice": {"type": "function", "name": "get_weather"},
    },
}


@pytest.mark.parametrize("name", list(_FIXTURES))
def test_recorded_request_round_trips(name: str):
    body = _record(**_FIXTURES[name])

    request = ResponsesRequest(**body)

    _assert_preserved(body, request.model_dump(exclude_none=True))


@pytest.mark.parametrize("tool_choice", ["auto", "none", "required"])
def test_recorded_tool_choice_options_round_trip(tool_choice: str):
    body = _record(model="m", input="hi", tool_choice=tool_choice)

    request = ResponsesRequest(**body)

    _assert_preserved(body, request.model_dump(exclude_none=True))


def _assert_preserved(expected: Any, actual: Any, path: str = "$") -> None:
    """Asserts that `actual` contains everything `expected` does."""
    if isinstance(expected, dict):
        assert isinstance(actual, dict), path
        for key, value in expected.items():
            assert key in actual, f"{path}.{key} is lost"
            _assert_preserved(value, actual[key], f"{path}.{key}")
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected), path
        for idx, value in enumerate(expected):
            _assert_preserved(value, actual[idx], f"{path}[{idx}]")
    else:
        assert actual == expected, path


def test_the_round_trip_check_detects_a_lost_field():
    with pytest.raises(AssertionError, match=r"\$\.metadata\.k is lost"):
        _assert_preserved({"metadata": {"k": "v"}}, {"metadata": {}})


def test_tools_resolve_to_their_models():
    body = _record(**_FIXTURES["tools"])

    request = ResponsesRequest(**body)

    assert request.tools is not None
    assert [type(tool).__name__ for tool in request.tools] == [
        "FunctionTool",
        "CustomTool",
        "Tool",
        "Tool",
    ]
    assert request.tools[2].model_dump()["search_context_size"] == "low"


def test_malformed_function_tool_is_an_error():
    with pytest.raises(ValidationError):
        model_parse(
            ResponsesRequest, {"input": "hi", "tools": [{"type": "function"}]}
        )


def test_input_is_required():
    with pytest.raises(ValidationError):
        model_parse(ResponsesRequest, {"model": "m"})


async def _from_request(body: dict[str, Any]) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "headers": [(b"api-key", b"key")],
        "query_string": b"",
    }
    body_bytes = json.dumps(body).encode()

    async def receive():
        return {"type": "http.request", "body": body_bytes}

    return await Request.from_request(
        fastapi.Request(scope, receive),
        deployment_id="deployment",
        base_url=None,
    )


async def test_deployment_fields_are_kept_apart_from_the_body():
    body = _record(**_FIXTURES["tool-traffic"])

    request = await _from_request(body)

    assert isinstance(request.context, RequestContext)
    assert request.context.api_key == "key"
    assert request.context.deployment_id == "deployment"
    assert not hasattr(request, "api_key")
    assert request.model_dump() == ResponsesRequest(**body).model_dump()


@pytest.mark.parametrize(
    "field, value",
    [
        ("deployment_id", "body"),
        ("headers", {"k": "v"}),
        ("base_url", "http://body.test"),
        ("api_key", "body"),
        ("conversation_id", "body"),
    ],
)
async def test_body_field_named_like_a_deployment_field_is_an_extra(
    field: str, value: Any
):
    request = await _from_request({"input": "hi", field: value})

    assert request.model_dump()[field] == value
    assert request.context.deployment_id == "deployment"
    assert request.context.api_key == "key"
    assert request.context.base_url is None
    assert request.context.conversation_id is None
    assert "k" not in request.context.headers


async def test_body_field_deployment_is_rejected():
    with pytest.raises(InvalidRequestError, match="'context'") as exc_info:
        await _from_request({"input": "hi", "context": {}})

    assert exc_info.value.status_code == 400


@pytest.mark.parametrize(
    "field, value",
    [
        ("store", True),
        ("background", True),
        ("previous_response_id", "resp_1"),
        ("conversation", "conv_1"),
        ("conversation", {"id": "conv_1"}),
    ],
)
def test_stateful_fields_are_rejected_with_422(field: str, value: Any):
    with pytest.raises(RequestValidationError, match=field) as exc_info:
        model_parse(ResponsesRequest, {"input": "hi", field: value})

    assert exc_info.value.status_code == 422


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {"store": False},
        {"background": False},
        {"previous_response_id": None},
        {"conversation": None},
        {"store": None, "background": None},
    ],
)
def test_stateless_values_of_stateful_fields_are_accepted(
    fields: dict[str, Any],
):
    model_parse(ResponsesRequest, {"input": "hi", **fields})


async def test_stateful_field_is_rejected_on_parsing_the_http_request():
    with pytest.raises(RequestValidationError) as exc_info:
        await _from_request({"input": "hi", "store": True})

    assert exc_info.value.status_code == 422


def test_string_input_is_normalized_to_a_user_message():
    request = model_parse(ResponsesRequest, {"input": "hello"})

    [item] = request.input_items
    assert isinstance(item, InputMessage)
    assert item.role == InputRole.USER
    assert isinstance(item.content, list)
    assert [type(part) for part in item.content] == [InputTextPart]
    assert request.messages == [item]
    assert request.user_messages == [item]
    assert request.messages[-1].text() == "hello"


def test_messages_filter_the_tool_traffic_and_keep_the_order():
    request = model_parse(
        ResponsesRequest,
        {
            "input": [
                {"role": "developer", "content": "rules"},
                {"role": "user", "content": "first"},
                {
                    "type": "function_call",
                    "call_id": "c",
                    "name": "n",
                    "arguments": "{}",
                },
                {"type": "function_call_output", "call_id": "c", "output": "o"},
                {"type": "web_search_call", "id": "ws_1"},
                {"type": "reasoning", "id": "rs_1", "summary": []},
                {"type": "message", "role": "assistant", "content": "answer"},
                {"type": "item_reference", "id": "msg_0"},
                {"type": "message", "role": "user", "content": "second"},
            ]
        },
    )

    assert len(request.input_items) == 9
    assert [(m.role, m.text()) for m in request.messages] == [
        (InputRole.DEVELOPER, "rules"),
        (InputRole.USER, "first"),
        (InputRole.ASSISTANT, "answer"),
        (InputRole.USER, "second"),
    ]
    assert [m.text() for m in request.user_messages] == ["first", "second"]
    assert request.messages[-1].text() == "second"


def test_no_messages_in_the_input():
    request = model_parse(
        ResponsesRequest,
        {"input": [{"type": "item_reference", "id": "msg_0"}]},
    )

    assert request.messages == []
    assert request.user_messages == []


def _stateful_field_app() -> TestClient:
    app = DIALApp()

    async def parse(request: fastapi.Request) -> dict:
        await Request.from_request(request, "deployment", None)
        return {}

    app.add_api_route("/responses", parse, methods=["POST"])
    return TestClient(app)


@pytest.mark.parametrize(
    "field, value",
    [
        ("store", True),
        ("background", True),
        ("previous_response_id", "resp_1"),
        ("conversation", "conv_1"),
    ],
)
def test_stateful_field_yields_http_422(field: str, value: Any):
    response = _stateful_field_app().post(
        "/responses",
        headers={"api-key": "key"},
        json={"input": "hi", field: value},
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["type"] == "invalid_request_error"
    assert field in error["message"]


def test_stateless_request_is_accepted_over_http():
    response = _stateful_field_app().post(
        "/responses",
        headers={"api-key": "key"},
        json={"input": "hi", "store": False},
    )

    assert response.status_code == 200


async def _produce_output(request: Request, response: Response) -> None:
    with response.create_reasoning() as reasoning:
        reasoning.append_summary("Thinking").append_text("Hmm")
    with response.create_message(phase="commentary") as message:
        message.append_text("Checking")
    with response.create_function_call("get_weather", call_id="c1") as call:
        call.set_arguments({"city": "Paris"})
    with response.create_custom_tool_call("sql", call_id="c2") as custom:
        custom.set_input("SELECT 1")
    with response.create_web_search() as search:
        search.searching(query="weather")
    with response.create_image_generation() as image:
        image.set_result("aGk=")


def test_own_output_sent_back_as_input_is_accepted():
    # A client sends the output back with the next request, as is,
    # and openai's types ask to keep `phase` on assistant messages
    first = run_handler(_produce_output, stream=False)
    assert first.body is not None
    output = first.body["output"]

    async def check(request: Request, response: Response) -> None:
        [_, message] = request.messages
        assert message.phase == MessagePhase.COMMENTARY
        [part] = message.content
        assert isinstance(part, OutputTextPart)
        assert part.logprobs == []
        assert [type(item) for item in request.input_items[1:]] == [
            ReasoningInputItem,
            InputMessage,
            FunctionCallItem,
            CustomToolCallItem,
            RawItem,
            RawItem,
        ]
        response.append_text("ok")

    # `DIALApp` rejects extra request fields: none may be undeclared
    second = run_handler(
        check,
        stream=False,
        input=[{"role": "user", "content": "Hi"}, *output],
    )
    assert second.http.status_code == 200, second.http.text
