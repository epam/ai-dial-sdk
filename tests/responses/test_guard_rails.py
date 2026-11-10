"""
One test per guard rail, each asserting the message as well as the
raised `runtime_error`.
"""

from collections.abc import Callable
from typing import Any

import pytest

from aidial_sdk.responses.enums import ErrorCode
from aidial_sdk.responses.message import Message, RefusalPart, TextPart
from aidial_sdk.responses.models import SearchAction
from aidial_sdk.responses.reasoning import (
    Reasoning,
    ReasoningTextPart,
    SummaryPart,
)
from aidial_sdk.responses.response import Response
from aidial_sdk.responses.server_tool import ImageGeneration, WebSearch
from aidial_sdk.responses.tool_call import CustomToolCall, FunctionCall
from tests.responses.conftest import (
    _FixedIdContext,
    make_response,
    raises_runtime_error,
)


def _closed_message() -> Message:
    return Message(_FixedIdContext(stream=True)).close()


def _closed_text() -> TextPart:
    message = Message(_FixedIdContext(stream=True))
    return message.create_text().close()


def _closed_refusal() -> RefusalPart:
    message = Message(_FixedIdContext(stream=True))
    return message.create_refusal().close()


def _closed_reasoning() -> Reasoning:
    return Reasoning(_FixedIdContext(stream=True)).close()


def _closed_summary() -> SummaryPart:
    reasoning = Reasoning(_FixedIdContext(stream=True))
    return reasoning.create_summary().close()


def _closed_reasoning_text() -> ReasoningTextPart:
    reasoning = Reasoning(_FixedIdContext(stream=True))
    return reasoning.create_text().close()


def _closed_function_call() -> FunctionCall:
    return FunctionCall(_FixedIdContext(stream=True), "f").close()


def _closed_custom_tool_call() -> CustomToolCall:
    return CustomToolCall(_FixedIdContext(stream=True), "f").close()


def _closed_search() -> WebSearch:
    return WebSearch(_FixedIdContext(stream=True)).close()


def _closed_image() -> ImageGeneration:
    return ImageGeneration(_FixedIdContext(stream=True)).close()


# `append_*` / `add_*` on a closed builder


@pytest.mark.parametrize(
    "call, reason",
    [
        (
            lambda: _closed_text().append("a"),
            "append text to a closed text part",
        ),
        (
            lambda: _closed_text().add_url_citation("u"),
            "add an annotation to a closed text part",
        ),
        (
            lambda: _closed_text().add_logprobs([]),
            "add logprobs to a closed text part",
        ),
        (
            lambda: _closed_refusal().append("a"),
            "append refusal to a closed refusal part",
        ),
        (
            lambda: _closed_message().append_text("a"),
            "append text to a closed message",
        ),
        (
            lambda: _closed_message().append_refusal("a"),
            "append refusal to a closed message",
        ),
        (
            lambda: _closed_message().create_text(),
            "create a text part in a closed message",
        ),
        (
            lambda: _closed_message().create_refusal(),
            "create a refusal part in a closed message",
        ),
        (
            lambda: _closed_message().set_phase("commentary"),
            "set the phase of a closed message",
        ),
        (
            lambda: _closed_message().set_incomplete(),
            "set the status of a closed message",
        ),
        (
            lambda: _closed_summary().append("a"),
            "append text to a closed summary part",
        ),
        (
            lambda: _closed_summary().set_incomplete(),
            "set the status of a closed summary part",
        ),
        (
            lambda: _closed_reasoning_text().append("a"),
            "append text to a closed reasoning text part",
        ),
        (
            lambda: _closed_reasoning().append_summary("a"),
            "append summary to a closed reasoning item",
        ),
        (
            lambda: _closed_reasoning().append_text("a"),
            "append text to a closed reasoning item",
        ),
        (
            lambda: _closed_reasoning().create_summary(),
            "create a summary part in a closed reasoning item",
        ),
        (
            lambda: _closed_reasoning().create_text(),
            "create a text part in a closed reasoning item",
        ),
        (
            lambda: _closed_reasoning().set_encrypted_content("e"),
            "set the encrypted content of a closed reasoning item",
        ),
        (
            lambda: _closed_reasoning().set_incomplete(),
            "set the status of a closed reasoning item",
        ),
        (
            lambda: _closed_function_call().append_arguments("a"),
            "append arguments to a closed function call",
        ),
        (
            lambda: _closed_function_call().set_arguments({}),
            "set the arguments of a closed function call",
        ),
        (
            lambda: _closed_function_call().set_incomplete(),
            "set the status of a closed function call",
        ),
        (
            lambda: _closed_custom_tool_call().append_input("a"),
            "append input to a closed custom tool call",
        ),
        (
            lambda: _closed_custom_tool_call().set_input("a"),
            "set the input of a closed custom tool call",
        ),
        (
            lambda: _closed_search().searching(),
            "set the status of a closed web search",
        ),
        (
            lambda: _closed_search().set_action(SearchAction()),
            "set the action of a closed web search",
        ),
        (
            lambda: _closed_search().add_source("u"),
            "add a source to a closed web search",
        ),
        (
            lambda: _closed_image().generating(),
            "set the status of a closed image generation",
        ),
        (
            lambda: _closed_image().append_partial("a"),
            "append a partial image to a closed image generation",
        ),
        (
            lambda: _closed_image().set_result("a"),
            "set the result of a closed image generation",
        ),
    ],
)
def test_write_to_a_closed_builder(caplog, call, reason: str):
    with raises_runtime_error(caplog, f"Trying to {reason}"):
        call()


# `close()` on an already closed builder


@pytest.mark.parametrize(
    "closed, kind",
    [
        (_closed_message, "message"),
        (_closed_text, "text part"),
        (_closed_refusal, "refusal part"),
        (_closed_reasoning, "reasoning item"),
        (_closed_summary, "summary part"),
        (_closed_reasoning_text, "reasoning text part"),
        (_closed_function_call, "function call"),
        (_closed_custom_tool_call, "custom tool call"),
        (_closed_search, "web search"),
        (_closed_image, "image generation"),
    ],
)
def test_close_a_closed_builder(caplog, closed, kind: str):
    builder = closed()

    with raises_runtime_error(caplog, f"Trying to close a closed {kind}"):
        builder.close()


# `set_arguments` / `set_input` once there are arguments / input


@pytest.mark.parametrize(
    "builder, first, second, reason",
    [
        (
            FunctionCall,
            lambda c: c.set_arguments("{}"),
            lambda c: c.set_arguments({"a": 1}),
            "set the arguments of a function call that already has arguments",
        ),
        (
            FunctionCall,
            lambda c: c.append_arguments("{"),
            lambda c: c.set_arguments({"a": 1}),
            "set the arguments of a function call that already has arguments",
        ),
        (
            CustomToolCall,
            lambda c: c.set_input("a"),
            lambda c: c.set_input("b"),
            "set the input of a custom tool call that already has input",
        ),
        (
            CustomToolCall,
            lambda c: c.append_input("a"),
            lambda c: c.set_input("b"),
            "set the input of a custom tool call that already has input",
        ),
    ],
)
def test_one_shot_setter_called_again(
    caplog, builder, first, second, reason: str
):
    call = builder(_FixedIdContext(stream=True), "f")
    first(call)

    with raises_runtime_error(caplog, f"Trying to {reason}"):
        second(call)


# `set_response_id` / `set_created` / `set_model` after start of generation


def _started(stream: bool = True) -> Response:
    response = make_response(stream=stream)
    response.create_message()
    return response


@pytest.mark.parametrize(
    "call, reason",
    [
        (
            lambda: _started().set_response_id("r"),
            'Trying to set "response_id" after start of generation',
        ),
        (
            lambda: _started().set_created(1),
            'Trying to set "created" after start of generation',
        ),
        (
            lambda: _started().set_model("m"),
            'Trying to set "model" after start of generation',
        ),
        (
            lambda: _started(stream=False).set_model("m"),
            'Trying to set "model" after start of generation',
        ),
        (
            # Headers too: once the stream is open, it's too late
            lambda: _started().append_header("a", "1"),
            "Trying to set a header after start of generation",
        ),
    ],
)
def test_setter_after_start_of_generation(caplog, call, reason: str):
    with raises_runtime_error(caplog, reason):
        call()


@pytest.mark.parametrize("stream", [True, False])
@pytest.mark.parametrize(
    "first_event",
    [
        lambda response: response.create_message(),
        lambda response: response.error(ErrorCode.SERVER_ERROR, "Odd"),
        lambda response: response.unsafe_emit({"type": "x"}),
    ],
)
def test_generation_starts_alike_in_both_modes(
    caplog, stream: bool, first_event: Callable[[Response], Any]
):
    response = make_response(stream=stream)
    first_event(response)

    with raises_runtime_error(
        caplog, 'Trying to set "model" after start of generation'
    ):
        response.set_model("x")


# `set_usage` called twice


def test_set_usage_twice(caplog):
    response = make_response(stream=True).set_usage(1, 1)

    with raises_runtime_error(caplog, 'Trying to set "usage" twice'):
        response.set_usage(1, 1)


# `set_incomplete` where the item type has no `incomplete` status: the
# method doesn't exist, a type error rather than a runtime one


@pytest.mark.parametrize(
    "builder, has_it",
    [
        (Message, True),
        (Reasoning, True),
        (FunctionCall, True),
        (SummaryPart, True),
        (TextPart, False),
        (RefusalPart, False),
        (ReasoningTextPart, False),
        (CustomToolCall, False),
        (WebSearch, False),
        (ImageGeneration, False),
    ],
)
def test_set_incomplete_exists_only_where_the_schema_admits_it(
    builder: type, has_it: bool
):
    assert hasattr(builder, "set_incomplete") == has_it
