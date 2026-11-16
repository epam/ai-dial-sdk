"""
Delta streams auto-flush, and mutators return `self`, so the fluent form
produces the same stream as the `with` form. Two calls in flight are
`test_response.test_two_function_calls`.
"""

import pytest

from aidial_sdk.responses._context import _ResponseContext
from aidial_sdk.responses.enums import ErrorCode
from aidial_sdk.responses.message import Message
from aidial_sdk.responses.models import Logprob, SearchAction, UrlCitation
from aidial_sdk.responses.reasoning import Reasoning
from aidial_sdk.responses.request import Request
from aidial_sdk.responses.response import Response, _Producer
from aidial_sdk.responses.server_tool import ImageGeneration, WebSearch
from aidial_sdk.responses.tool_call import CustomToolCall, FunctionCall
from tests.responses.conftest import (
    _FixedIdContext,
    drain,
    make_response,
    run_response,
)


def _types(ctx: _ResponseContext) -> list[str]:
    return [event["type"] for event in drain(ctx)]


# The next event on the same item flushes the open delta stream


def test_opening_a_part_flushes_the_open_one():
    ctx = _FixedIdContext(stream=True)
    message = Message(ctx)
    text = message.create_text().append("a")
    drain(ctx)

    refusal = message.create_refusal()

    assert text.closed and not refusal.closed
    assert _types(ctx) == [
        "response.output_text.done",
        "response.content_part.done",
        "response.content_part.added",
    ]


def test_opening_a_part_of_the_same_kind_flushes_the_open_one():
    ctx = _FixedIdContext(stream=True)
    message = Message(ctx)
    first = message.create_text()
    second = message.create_text()

    assert first.closed and not second.closed
    assert (first._index, second._index) == (0, 1)


def test_closing_the_message_closes_its_open_part():
    ctx = _FixedIdContext(stream=True)
    message = Message(ctx)
    refusal = message.create_refusal()
    drain(ctx)

    message.close()

    assert refusal.closed
    assert _types(ctx) == [
        "response.refusal.done",
        "response.content_part.done",
        "response.output_item.done",
    ]


def test_opening_a_text_part_flushes_the_open_summary():
    ctx = _FixedIdContext(stream=True)
    reasoning = Reasoning(ctx)
    summary = reasoning.create_summary()
    drain(ctx)

    text = reasoning.create_text()

    assert summary.closed and not text.closed
    assert [e["type"] for e in drain(ctx)] == [
        "response.reasoning_summary_text.done",
        "response.reasoning_summary_part.done",
        "response.content_part.added",
    ]


def test_opening_a_summary_flushes_the_open_text_part():
    ctx = _FixedIdContext(stream=True)
    reasoning = Reasoning(ctx)
    text = reasoning.create_text()
    drain(ctx)

    summary = reasoning.create_summary()

    assert text.closed and not summary.closed
    assert [e["type"] for e in drain(ctx)] == [
        "response.reasoning_text.done",
        "response.content_part.done",
        "response.reasoning_summary_part.added",
    ]


@pytest.mark.parametrize(
    "create, done",
    [
        (
            Reasoning.create_summary,
            [
                "response.reasoning_summary_text.done",
                "response.reasoning_summary_part.done",
            ],
        ),
        (
            Reasoning.create_text,
            ["response.reasoning_text.done", "response.content_part.done"],
        ),
    ],
)
def test_closing_the_reasoning_closes_its_open_part(create, done: list[str]):
    ctx = _FixedIdContext(stream=True)
    reasoning = Reasoning(ctx)
    part = create(reasoning)
    drain(ctx)

    reasoning.close()

    assert part.closed
    assert [e["type"] for e in drain(ctx)] == [
        *done,
        "response.output_item.done",
    ]


# Every mutator returns `self`


def test_message_mutators_return_self():
    ctx = _FixedIdContext(stream=True)
    message = Message(ctx)
    text = message.create_text()
    logprob = Logprob(
        token="a",  # noqa: S106
        bytes=[97],
        logprob=0.0,
        top_logprobs=[],
    )
    citation = UrlCitation(url="u", title="", start_index=0, end_index=0)

    assert text.append("a") is text
    assert text.add_annotation(citation) is text
    assert text.add_url_citation("u") is text
    assert text.add_logprobs([logprob]) is text
    assert message.append_text("a") is message
    assert message.append_refusal("a") is message
    assert message.set_phase("commentary") is message
    assert message.set_incomplete() is message

    refusal = message.create_refusal()
    assert refusal.append("a") is refusal


def test_reasoning_mutators_return_self():
    reasoning = Reasoning(_FixedIdContext(stream=True))
    summary = reasoning.create_summary()
    assert summary.append("a") is summary
    assert summary.set_incomplete() is summary

    text = reasoning.create_text()
    assert text.append("a") is text
    assert reasoning.append_summary("a") is reasoning
    assert reasoning.append_text("a") is reasoning
    assert reasoning.set_encrypted_content("e") is reasoning
    assert reasoning.set_incomplete() is reasoning


def test_tool_call_mutators_return_self():
    function_call = FunctionCall(_FixedIdContext(stream=True), "f")
    custom_tool_call = CustomToolCall(_FixedIdContext(stream=True), "f")

    # The setters are one shot, so they go before the appends
    assert function_call.set_arguments("a") is function_call
    assert function_call.append_arguments("a") is function_call
    assert function_call.set_incomplete() is function_call
    assert custom_tool_call.set_input("a") is custom_tool_call
    assert custom_tool_call.append_input("a") is custom_tool_call


def test_server_tool_mutators_return_self():
    search = WebSearch(_FixedIdContext(stream=True))
    image = ImageGeneration(_FixedIdContext(stream=True))

    assert search.searching() is search
    assert search.add_source("u") is search
    assert search.set_action(SearchAction()) is search
    assert image.generating() is image
    assert image.append_partial("a") is image
    assert image.set_result("a") is image


def test_response_mutators_return_self():
    response = make_response(stream=True)

    assert response.set_response_id("r") is response
    assert response.set_created(1) is response
    assert response.set_model("m") is response
    assert response.append_header("a", "1") is response
    assert response.set_usage(1, 1) is response
    assert response.set_incomplete("content_filter") is response
    assert response.append_text("a") is response
    assert response.append_refusal("b") is response


def test_error_and_fail_return_self():
    response = make_response(stream=True)

    assert response.error(ErrorCode.SERVER_ERROR, "a") is response
    assert response.fail(ErrorCode.SERVER_ERROR, "b") is response


# The fluent form and the `with` form produce the same transcript.
# Each is followed by another item: were `close()` not to close the
# ancestors, the clean return would close them after that item instead.


async def _fluent_message(request: Request, response: Response) -> None:
    response.create_message().create_text().append("Hello").close()
    response.create_function_call("next", call_id="c").close()


async def _with_message(request: Request, response: Response) -> None:
    with response.create_message() as message, message.create_text() as text:
        text.append("Hello")
    response.create_function_call("next", call_id="c").close()


async def _fluent_reasoning(request: Request, response: Response) -> None:
    response.create_reasoning().create_summary().append("Thinking").close()
    response.create_function_call("next", call_id="c").close()


async def _with_reasoning(request: Request, response: Response) -> None:
    with (
        response.create_reasoning() as reasoning,
        reasoning.create_summary() as summary,
    ):
        summary.append("Thinking")
    response.create_function_call("next", call_id="c").close()


async def _fluent_function_call(request: Request, response: Response) -> None:
    response.create_function_call("f").append_arguments("{}").close()
    response.append_text("Done")


async def _with_function_call(request: Request, response: Response) -> None:
    with response.create_function_call("f") as call:
        call.append_arguments("{}")
    response.append_text("Done")


@pytest.mark.parametrize(
    "fluent, nested",
    [
        (_fluent_message, _with_message),
        (_fluent_reasoning, _with_reasoning),
        (_fluent_function_call, _with_function_call),
    ],
    ids=["message", "reasoning", "function_call"],
)
async def test_fluent_and_with_forms_produce_the_same_transcript(
    fluent: _Producer, nested: _Producer
):
    assert (await run_response(fluent)).transcript == (
        await run_response(nested)
    ).transcript
