"""
Conformance over HTTP, and proof that the checks can fail.

`run_handler` and `check_http` run these checks on every response they see,
`drain`, `run_builders` and `run_response` on every event, so the rest of the
suite checks conformance too. The tests here make sure that, between them,
the handlers below put every in-scope event type on the wire, and that a
malformed event or body does not get past the checks.
"""

from typing import Any, get_args

import httpx2
import pytest
from openai.types.responses import ResponseStreamEvent

from aidial_sdk.responses import events
from aidial_sdk.responses.enums import ErrorCode, IncompleteReason
from aidial_sdk.responses.models import ResponseObject
from aidial_sdk.responses.request import Request
from aidial_sdk.responses.response import Response
from tests.responses.conftest import (
    Handler,
    ValidationError,
    check_http,
    run_handler,
    validate_event,
    validate_response,
    validate_stream,
)

# The 32 event types the builders produce
_IN_SCOPE = {
    "response.created",
    "response.in_progress",
    "response.completed",
    "response.incomplete",
    "response.failed",
    "error",
    "response.output_item.added",
    "response.output_item.done",
    "response.content_part.added",
    "response.content_part.done",
    "response.output_text.delta",
    "response.output_text.done",
    "response.output_text.annotation.added",
    "response.refusal.delta",
    "response.refusal.done",
    "response.reasoning_summary_part.added",
    "response.reasoning_summary_text.delta",
    "response.reasoning_summary_text.done",
    "response.reasoning_summary_part.done",
    "response.reasoning_text.delta",
    "response.reasoning_text.done",
    "response.function_call_arguments.delta",
    "response.function_call_arguments.done",
    "response.custom_tool_call_input.delta",
    "response.custom_tool_call_input.done",
    "response.web_search_call.in_progress",
    "response.web_search_call.searching",
    "response.web_search_call.completed",
    "response.image_generation_call.in_progress",
    "response.image_generation_call.generating",
    "response.image_generation_call.partial_image",
    "response.image_generation_call.completed",
}


def _openai_event_types() -> set[str]:
    union, *_ = get_args(ResponseStreamEvent)  # Annotated[Union, ...]
    return {
        value
        for event in get_args(union)
        # `__annotations__` as in test_enums: `model_fields` is pydantic v2 only
        for value in get_args(event.__annotations__["type"])
    }


def test_in_scope_event_types_are_openai_event_types():
    openai_types = _openai_event_types()

    assert len(openai_types) == 53
    assert len(_IN_SCOPE) == 32
    assert _IN_SCOPE.issubset(openai_types)


async def _every_item(request: Request, response: Response) -> None:
    with response.create_message() as message:
        with message.create_text() as text:
            text.append("Hello").add_url_citation("https://example.com")
        with message.create_refusal() as refusal:
            refusal.append("No")

    with response.create_reasoning() as reasoning:
        reasoning.append_summary("Thought").append_text("Thinking")

    with response.create_function_call("f") as call:
        call.append_arguments('{"a":').append_arguments(" 1}")

    with response.create_custom_tool_call("g") as custom:
        custom.append_input("x")

    with response.create_web_search() as search:
        search.searching(query="q").add_source("https://example.com")

    with response.create_image_generation() as image:
        image.generating().append_partial("aGk=").set_result("aGk=")

    response.set_usage(1, 2)


async def _incomplete(request: Request, response: Response) -> None:
    response.append_text("Cut")
    response.set_incomplete(IncompleteReason.MAX_OUTPUT_TOKENS)


async def _failed(request: Request, response: Response) -> None:
    response.append_text("Partial")
    response.fail(ErrorCode.SERVER_ERROR, "Down")


_HANDLERS: dict[str, tuple[Handler, str]] = {
    "every_item": (_every_item, "completed"),
    "incomplete": (_incomplete, "incomplete"),
    "failed": (_failed, "failed"),
}


def test_every_in_scope_event_type_conforms():
    """
    `check_http` validates each stream, and the streams cover all 32
    in-scope event types between them.
    """
    seen: set[str] = set()
    for handler, status in _HANDLERS.values():
        run = run_handler(handler, stream=True)

        assert run.http.status_code == 200
        assert run.body is not None
        assert run.body["status"] == status
        assert run.types[-1] == f"response.{status}"
        seen |= set(run.types)

    assert seen == _IN_SCOPE


@pytest.mark.parametrize("name", list(_HANDLERS))
def test_block_body_conforms(name: str):
    """`check_http` validates the body."""
    handler, status = _HANDLERS[name]

    run = run_handler(handler, stream=False)

    assert run.http.status_code == 200
    assert run.http.headers["content-type"] == "application/json"
    assert run.body is not None
    assert run.body["status"] == status


# The checks must be able to fail: a validator that never fails is worse
# than none. Each case breaks a valid event in a single way.

_DELTA = events.output_text_delta(
    item_id="msg_1", output_index=0, content_index=0, delta="Hi", logprobs=[]
)
_DELTA["sequence_number"] = 0

_RESPONSE_OBJECT = ResponseObject(id="resp_1", created_at=0, model="m")
_FAILED = events.response_failed(response=_RESPONSE_OBJECT)
_FAILED["sequence_number"] = 0
_FAILED["response"].update(
    status="failed", error={"code": "server_error", "message": "Down"}
)


def _with(event: dict, **fields: Any) -> dict:
    return {**event, **fields}


def _without(event: dict, key: str) -> dict:
    return {k: v for k, v in event.items() if k != key}


def _with_error(**error: Any) -> dict:
    return {**_FAILED, "response": {**_FAILED["response"], "error": error}}


def test_valid_cases_pass():
    # Otherwise the cases below would fail for the wrong reason
    validate_event(_DELTA)
    validate_event(_FAILED)
    validate_response(_FAILED["response"])


@pytest.mark.parametrize(
    "event, exception",
    [
        pytest.param(
            _without(_DELTA, "delta"), ValidationError, id="missing-field"
        ),
        pytest.param(
            _with(_DELTA, output_index="first"),
            ValidationError,
            id="wrong-value-type",
        ),
        pytest.param(
            _with(_DELTA, type="response.output_text.deltas"),
            ValidationError,
            id="unknown-type",
        ),
        pytest.param(
            _with(_DELTA, display_message="Hi"),
            AssertionError,
            id="extra-field",
        ),
        pytest.param(
            _with_error(code="invalid_request_error", message="Bad"),
            ValidationError,
            id="error-code-out-of-enum",
        ),
        pytest.param(
            # DIAL's error envelope
            _with_error(
                code="server_error", message="Down", display_message="Down"
            ),
            AssertionError,
            id="nested-extra-field",
        ),
    ],
)
def test_malformed_event_is_rejected(event: dict, exception: type[Exception]):
    with pytest.raises(exception):
        validate_event(event)


@pytest.mark.parametrize(
    "response, exception",
    [
        pytest.param(
            _without(_FAILED["response"], "output"),
            ValidationError,
            id="missing-field",
        ),
        pytest.param(
            {**_FAILED["response"], "status": "done"},
            ValidationError,
            id="status-out-of-enum",
        ),
        pytest.param(
            _with_error(code="server_error", message="Down", type="x")[
                "response"
            ],
            AssertionError,
            id="nested-extra-field",
        ),
    ],
)
def test_malformed_response_is_rejected(
    response: dict, exception: type[Exception]
):
    with pytest.raises(exception):
        validate_response(response)


@pytest.mark.parametrize(
    "numbers", [[0, 2], [0, 0], [1, 2]], ids=["gap", "repeat", "offset"]
)
def test_sequence_numbers_out_of_order_are_rejected(numbers: list[int]):
    stream = [_with(_DELTA, sequence_number=n) for n in numbers]

    with pytest.raises(AssertionError):
        validate_stream(stream)


def test_done_terminator_is_rejected():
    run = run_handler(_incomplete, stream=True)
    http = httpx2.Response(
        200,
        headers={"content-type": "text/event-stream"},
        text=run.http.text + "data: [DONE]\n\n",
    )

    with pytest.raises(AssertionError):
        check_http(http)


async def _emits_malformed_event(request: Request, response: Response) -> None:
    response.unsafe_emit(_without(_DELTA, "delta"))


def test_run_handler_rejects_a_malformed_event():
    # The checks are wired into the harness, not only defined
    with pytest.raises(ValidationError):
        run_handler(_emits_malformed_event, stream=True)
