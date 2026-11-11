import asyncio

import pytest

from aidial_sdk.responses.enums import IncompleteReason
from aidial_sdk.responses.message import Message
from aidial_sdk.responses.reasoning import Reasoning
from aidial_sdk.responses.request import Request
from aidial_sdk.responses.response import Response
from aidial_sdk.responses.server_tool import ImageGeneration, WebSearch
from aidial_sdk.responses.tool_call import CustomToolCall, FunctionCall
from tests.responses.conftest import (
    drain,
    make_request,
    make_response,
    run_response,
)
from tests.responses.test_reference import (
    open_items_at_return,
    shortcuts,
    two_function_calls,
)


async def test_two_function_calls():
    run = await run_response(two_function_calls)

    deltas = [
        (e["item_id"], e["output_index"], e["delta"])
        for e in run.stream
        if e["type"] == "response.function_call_arguments.delta"
    ]
    assert deltas == [
        ("fc_1", 0, '{"city":'),
        ("fc_2", 1, '{"tz":'),
        ("fc_1", 0, ' "Paris"}'),
        ("fc_2", 1, ' "CET"}'),
    ]


async def test_open_items_are_closed_at_return_in_creation_order():
    run = await run_response(open_items_at_return)

    *_, message_done, reasoning_done, completed = [
        e
        for e in run.stream
        if e["type"] in ("response.output_item.done", "response.completed")
    ]
    assert message_done["output_index"] == 0
    assert reasoning_done["output_index"] == 2
    assert completed["type"] == "response.completed"
    assert {item["status"] for item in run.body["output"]} == {"completed"}


async def test_an_empty_handler_completes():
    async def producer(request: Request, response: Response) -> None:
        pass

    run = await run_response(producer)

    assert run.types == [
        "response.created",
        "response.in_progress",
        "response.completed",
    ]
    assert run.body["output"] == []
    assert run.body["status"] == "completed"


async def test_preamble_is_held_back_until_the_first_item():
    response = make_response(stream=True)

    assert drain(response._ctx) == []

    response.create_message()

    assert [e["type"] for e in drain(response._ctx)] == [
        "response.created",
        "response.in_progress",
        "response.output_item.added",
    ]


async def test_factories():
    response = make_response(stream=True)

    message = response.create_message(phase="commentary")
    reasoning = response.create_reasoning()
    function_call = response.create_function_call("f", call_id="call_f")
    custom_tool_call = response.create_custom_tool_call("c")
    web_search = response.create_web_search()
    image_generation = response.create_image_generation()

    builders = (
        message,
        reasoning,
        function_call,
        custom_tool_call,
        web_search,
        image_generation,
    )
    types = (
        Message,
        Reasoning,
        FunctionCall,
        CustomToolCall,
        WebSearch,
        ImageGeneration,
    )
    assert response.items == builders
    assert [type(b) for b in builders] == list(types)
    assert [b.output_index for b in builders] == list(range(6))
    assert message._item.phase == "commentary"
    assert function_call.call_id == "call_f"
    assert response._ctx.response_object.output == [b._item for b in builders]


def test_defaults():
    request = make_request(stream=True)
    response = Response(request)
    response_object = response._ctx.response_object

    assert response.stream is True
    assert response._ctx.stream is True
    assert response.items == ()
    assert response_object.model == "deployment"
    assert response_object.id.startswith("resp_")
    assert len(response_object.id) == len("resp_") + 32


_PARAMETERS = {
    "instructions": "Be brief",
    "tools": [
        {"type": "function", "name": "f", "parameters": {}, "strict": True},
        {"type": "custom", "name": "c"},
        {"type": "web_search"},
    ],
    "tool_choice": {"type": "function", "name": "f"},
    "parallel_tool_calls": False,
    "max_tool_calls": 3,
    "text": {"format": {"type": "text"}, "verbosity": "low"},
    "reasoning": {"effort": "low", "summary": "auto"},
    "temperature": 0.3,
    "top_p": 0.9,
    "top_logprobs": 2,
    "max_output_tokens": 100,
    "truncation": "disabled",
    "metadata": {"k": "v"},
    "user": "u",
    "prompt_cache_key": "p",
    "safety_identifier": "s",
}


async def test_request_parameters_are_echoed():
    async def producer(request: Request, response: Response) -> None:
        response.append_text("Hi")

    run = await run_response(producer, **_PARAMETERS)

    for event in (run.stream[0], run.stream[1], run.stream[-1]):
        echoed = {key: event["response"][key] for key in _PARAMETERS}
        assert echoed == _PARAMETERS


async def test_absent_request_parameters_take_the_defaults():
    async def producer(request: Request, response: Response) -> None:
        pass

    run = await run_response(producer, tool_choice="required")

    assert run.body["tool_choice"] == "required"
    assert run.body["tools"] == []
    assert run.body["parallel_tool_calls"] is True
    required = {"tools", "tool_choice", "parallel_tool_calls"}
    for key in _PARAMETERS.keys() - required:
        assert run.body[key] is None, key


async def test_aflush_waits_for_the_events_to_be_written():
    response = make_response(stream=True)
    response.create_message()
    written = []

    async def consume() -> None:
        for _ in range(3):
            written.append(await response._ctx._queue.get())
            response._ctx._queue.task_done()

    consumer = asyncio.create_task(consume())
    await asyncio.wait_for(response.aflush(), timeout=1)

    assert len(written) == 3
    await consumer


async def test_aflush_in_block_mode():
    response = make_response(stream=False)
    response.create_message().append_text("Hi")

    await asyncio.wait_for(response.aflush(), timeout=1)


async def test_shortcuts_go_to_a_default_message():
    run = await run_response(shortcuts)

    message, function_call = run.body["output"]
    assert message["content"] == [
        {
            "type": "output_text",
            "text": "Let me check.",
            "annotations": [],
            "logprobs": [],
        },
        {"type": "refusal", "refusal": "No."},
        {
            "type": "output_text",
            "text": "Sorry.",
            "annotations": [],
            "logprobs": [],
        },
    ]
    assert function_call["type"] == "function_call"


async def test_shortcuts_create_another_message_once_it_is_closed():
    async def producer(request: Request, response: Response) -> None:
        response.append_text("One")
        response.items[0].close()
        response.append_text("Two")

    run = await run_response(producer)

    assert [item["content"][0]["text"] for item in run.body["output"]] == [
        "One",
        "Two",
    ]


@pytest.mark.parametrize(
    "reason", [IncompleteReason.MAX_OUTPUT_TOKENS, "content_filter"]
)
async def test_set_incomplete(reason):
    async def producer(request: Request, response: Response) -> None:
        response.append_text("Trunc")
        response.set_incomplete(reason)

    run = await run_response(producer)

    assert run.types[-1] == "response.incomplete"
    assert "response.completed" not in run.types
    assert run.body["status"] == "incomplete"
    assert run.body["incomplete_details"] == {
        "reason": IncompleteReason(reason)
    }
    # The message cut off is incomplete too
    assert run.body["output"][0]["status"] == "incomplete"


async def _cut_off_with_items_open(
    request: Request, response: Response
) -> None:
    response.create_message().append_text("Done").close()
    response.create_reasoning().append_summary("Think")
    response.create_function_call("f").append_arguments('{"a":')
    response.create_custom_tool_call("c").append_input("SEL")
    response.create_web_search()
    response.set_incomplete(IncompleteReason.MAX_OUTPUT_TOKENS)


async def test_set_incomplete_closes_the_open_items_as_incomplete():
    run = await run_response(_cut_off_with_items_open)

    statuses = [item.get("status") for item in run.body["output"]]
    # Closed by the handler, then the three types that admit `incomplete`;
    # a custom tool call has no status, a web search no `incomplete`
    assert statuses == [
        "completed",
        "incomplete",
        "incomplete",
        None,
        "completed",
    ]


async def test_set_usage():
    async def producer(request: Request, response: Response) -> None:
        response.set_usage(10, 5)
        response.append_text("Hi")

    run = await run_response(producer)

    assert run.stream[0]["response"]["usage"] is None
    assert run.body["usage"] == {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
        "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
        "output_tokens_details": {"reasoning_tokens": 0},
    }


async def test_set_usage_details():
    async def producer(request: Request, response: Response) -> None:
        response.set_usage(
            10,
            5,
            cached_tokens=3,
            cache_write_tokens=2,
            reasoning_tokens=4,
        )

    run = await run_response(producer)

    assert run.body["usage"]["input_tokens_details"] == {
        "cached_tokens": 3,
        "cache_write_tokens": 2,
    }
    assert run.body["usage"]["output_tokens_details"] == {"reasoning_tokens": 4}


async def test_setters_before_generation_reach_every_lifecycle_event():
    async def producer(request: Request, response: Response) -> None:
        response.set_response_id("resp_x").set_created(1).set_model("gpt")
        response.append_text("Hi")

    run = await run_response(producer)

    lifecycle = [run.stream[0], run.stream[1], run.stream[-1]]
    for event in lifecycle:
        assert event["response"]["id"] == "resp_x"
        assert event["response"]["created_at"] == 1
        assert event["response"]["model"] == "gpt"


def test_append_header():
    response = make_response(stream=True)

    response.append_header("a", "1").append_header("b", "2")

    assert response._headers == [("a", "1"), ("b", "2")]


def test_append_header_after_start_of_generation_in_block_mode():
    # The headers are only sent with the body
    response = make_response(stream=False)
    response.append_text("Hi")

    response.append_header("a", "1")

    assert response._headers == [("a", "1")]
