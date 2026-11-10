"""
One fixed call sequence per case, its SSE transcript compared byte for
byte with `golden/<case>.sse`.

A builder case runs its builders against a bare context (`run_builders`),
a response case runs as the handler of a whole response (`run_response`).
Both check every event against openai and the stream against the block
response. `UPDATE_GOLDEN=1` rewrites the files: read every one before
committing it, and treat a diff as a finding, not something to regenerate
away.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from aidial_sdk.responses._context import _ResponseContext
from aidial_sdk.responses.message import Message
from aidial_sdk.responses.models import (
    FileCitation,
    Logprob,
    LogprobTopLogprob,
    OpenPageAction,
)
from aidial_sdk.responses.reasoning import Reasoning
from aidial_sdk.responses.request import Request
from aidial_sdk.responses.response import Response, _Producer
from aidial_sdk.responses.server_tool import ImageGeneration, WebSearch
from aidial_sdk.responses.tool_call import CustomToolCall, FunctionCall
from tests.responses.conftest import assert_golden, run_builders, run_response


class _Boom(Exception):
    pass


# message


def _message_text(ctx: _ResponseContext) -> None:
    with Message(ctx, phase="final_answer") as message:
        message.append_text("Hello").append_text(", world")


def _message_text_part(ctx: _ResponseContext) -> None:
    hello = Logprob(
        token="Hello",  # noqa: S106
        bytes=[72, 101, 108, 108, 111],
        logprob=-0.1,
        top_logprobs=[
            LogprobTopLogprob(token="Hi", bytes=[72, 105], logprob=-2.5)  # noqa: S106
        ],
    )
    with Message(ctx) as message, message.create_text() as text:
        text.add_logprobs([hello]).append("Hello")
        text.append("!")


def _message_annotation(ctx: _ResponseContext) -> None:
    with Message(ctx) as message, message.create_text() as text:
        text.append("See the docs")
        text.add_url_citation("https://example.com")
        text.append(" and the file.")
        text.add_annotation(
            FileCitation(file_id="file_1", filename="a.txt", index=26)
        )
        text.add_url_citation(
            "https://example.org", title="Example", start_index=4, end_index=12
        )


def _message_refusal(ctx: _ResponseContext) -> None:
    with Message(ctx) as message, message.create_refusal() as refusal:
        refusal.append("I can't").append(" help with that.")


def _message_text_then_refusal(ctx: _ResponseContext) -> None:
    # Each part of another kind closes the one before it
    with Message(ctx) as message:
        message.append_text("Let me check.")
        message.append_refusal("No.")
        message.create_text().append("Sorry.")


def _message_trailing_logprobs(ctx: _ResponseContext) -> None:
    # No append follows the logprobs, so closing has to send them
    hi = Logprob(token="Hi", bytes=[72, 105], logprob=-0.2, top_logprobs=[])  # noqa: S106
    with Message(ctx) as message, message.create_text() as text:
        text.append("Hi").add_logprobs([hi])


def _message_incomplete(ctx: _ResponseContext) -> None:
    with Message(ctx) as message:
        message.append_text("Truncated mid-sen").set_incomplete()


# reasoning


def _reasoning_summary(ctx: _ResponseContext) -> None:
    with Reasoning(ctx) as reasoning:
        with reasoning.create_summary() as summary:
            summary.append("Thinking").append(" hard.")
        reasoning.append_summary("Second part.")


def _reasoning_text(ctx: _ResponseContext) -> None:
    with Reasoning(ctx) as reasoning, reasoning.create_text() as text:
        text.append("Step 1.").append(" Step 2.")


def _reasoning_summary_text_encrypted(ctx: _ResponseContext) -> None:
    # Each switch of array closes the open part,
    # so the second summary is a part of its own
    with Reasoning(ctx) as reasoning:
        reasoning.append_summary("Summary.")
        reasoning.append_text("Raw thoughts.")
        reasoning.append_summary("More summary.")
        reasoning.set_encrypted_content("gAAAAB")


def _reasoning_interrupted_summary(ctx: _ResponseContext) -> None:
    with Reasoning(ctx) as reasoning:
        reasoning.set_incomplete()
        with reasoning.create_summary() as summary:
            summary.append("Cut sh").set_incomplete()


# tool calls


def _function_call_streamed(ctx: _ResponseContext) -> None:
    with FunctionCall(ctx, "get_weather") as call:
        call.append_arguments('{"city":').append_arguments(' "Paris"}')


def _function_call_one_shot(ctx: _ResponseContext) -> None:
    with FunctionCall(ctx, "get_weather", call_id="call_abc") as call:
        call.set_arguments({"city": "Paris"})


def _custom_tool_call_streamed(ctx: _ResponseContext) -> None:
    with CustomToolCall(ctx, "run_sql") as call:
        call.append_input("SELECT 1").append_input(" FROM t")


def _custom_tool_call_one_shot(ctx: _ResponseContext) -> None:
    with CustomToolCall(ctx, "run_sql", call_id="call_abc") as call:
        call.set_input("SELECT 1")


def _function_call_incomplete(ctx: _ResponseContext) -> None:
    with FunctionCall(ctx, "get_weather") as call:
        call.append_arguments('{"city": "Par').set_incomplete()


# server-side tools


def _web_search(ctx: _ResponseContext) -> None:
    with WebSearch(ctx) as search:
        search.searching(query="weather in Paris")
        search.add_source("https://example.com/paris")
        search.add_source("https://example.org/weather")


def _web_search_open_page(ctx: _ResponseContext) -> None:
    with WebSearch(ctx) as search:
        search.searching()
        search.set_action(OpenPageAction(url="https://example.com"))


def web_search_failed(ctx: _ResponseContext) -> None:
    with pytest.raises(_Boom), WebSearch(ctx) as search:
        search.searching(queries=["a", "b"])
        raise _Boom()


def _image_generation(ctx: _ResponseContext) -> None:
    with ImageGeneration(ctx) as image:
        image.generating()
        image.append_partial("cGFydGlhbDE=").append_partial("cGFydGlhbDI=")
        image.set_result("cmVzdWx0")


def image_generation_failed(ctx: _ResponseContext) -> None:
    with pytest.raises(_Boom), ImageGeneration(ctx) as image:
        image.generating().append_partial("cGFydGlhbDE=")
        raise _Boom()


BUILDER_CASES: dict[str, Callable[[_ResponseContext], None]] = {
    "message_text": _message_text,
    "message_incomplete": _message_incomplete,
    "message_text_part": _message_text_part,
    "message_trailing_logprobs": _message_trailing_logprobs,
    "message_annotation": _message_annotation,
    "message_refusal": _message_refusal,
    "message_text_then_refusal": _message_text_then_refusal,
    "reasoning_summary": _reasoning_summary,
    "reasoning_text": _reasoning_text,
    "reasoning_summary_text_encrypted": _reasoning_summary_text_encrypted,
    "reasoning_interrupted_summary": _reasoning_interrupted_summary,
    "function_call_streamed": _function_call_streamed,
    "function_call_incomplete": _function_call_incomplete,
    "function_call_one_shot": _function_call_one_shot,
    "custom_tool_call_streamed": _custom_tool_call_streamed,
    "custom_tool_call_one_shot": _custom_tool_call_one_shot,
    "web_search": _web_search,
    "web_search_open_page": _web_search_open_page,
    "web_search_failed": web_search_failed,
    "image_generation": _image_generation,
    "image_generation_failed": image_generation_failed,
}


# whole responses


async def two_function_calls(request: Request, response: Response) -> None:
    weather = response.create_function_call("get_weather")
    time = response.create_function_call("get_time", call_id="call_t")

    weather.append_arguments('{"city":')
    time.append_arguments('{"tz":')
    weather.append_arguments(' "Paris"}')
    time.append_arguments(' "CET"}')

    weather.close()
    time.close()


async def open_items_at_return(request: Request, response: Response) -> None:
    # Left open: the message with its text part, and the reasoning item
    response.create_message().create_text().append("Hi")
    response.create_function_call("f").set_arguments("{}").close()
    response.create_reasoning().append_summary("Thinking")


async def shortcuts(request: Request, response: Response) -> None:
    response.append_text("Let me")
    response.append_text(" check.")
    response.append_refusal("No.")
    response.create_function_call("f").close()
    # The default message is still open: the text goes on in it
    response.append_text("Sorry.")


async def raises_in_message(request: Request, response: Response) -> None:
    with response.create_message() as message:
        message.append_text("Partial")
        raise _Boom()


async def raises_with_open_items(request: Request, response: Response) -> None:
    # Unlike on a clean return, the items open without a block stay open
    response.create_message().append_text("Partial")
    response.create_web_search().searching(query="q")
    response.create_function_call("f").append_arguments('{"a":')
    raise _Boom()


RESPONSE_CASES: dict[str, _Producer] = {
    "response_two_function_calls": two_function_calls,
    "response_open_items_at_return": open_items_at_return,
    "response_shortcuts": shortcuts,
    "response_raises_in_message": raises_in_message,
    "response_raises_with_open_items": raises_with_open_items,
}


@pytest.mark.parametrize("name", BUILDER_CASES)
async def test_builder_golden(name: str):
    assert_golden(name, await run_builders(BUILDER_CASES[name]))


@pytest.mark.parametrize("name", RESPONSE_CASES)
async def test_response_golden(name: str):
    run = await run_response(RESPONSE_CASES[name])
    assert_golden(name, run.transcript)


def test_every_golden_file_has_a_case():
    # A file no case writes is a stale transcript nobody checks
    on_disk = {
        path.stem for path in (Path(__file__).parent / "golden").glob("*")
    }
    assert on_disk == BUILDER_CASES.keys() | RESPONSE_CASES.keys()
