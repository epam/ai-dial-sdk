import logging
from collections.abc import Callable
from typing import Any

import pytest

from aidial_sdk._errors import INTERNAL_ERROR_MESSAGE
from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.exceptions import InternalServerError
from aidial_sdk.responses.enums import ErrorCode
from aidial_sdk.responses.events import _dump
from aidial_sdk.responses.request import Request
from aidial_sdk.responses.response import Response
from tests.responses.conftest import (
    make_response,
    raises_runtime_error,
    run_response,
)
from tests.responses.test_golden import (
    raises_in_message,
    raises_with_open_items,
)


class _Boom(Exception):
    pass


def _assert_failed(run: Any, code: str, message: str) -> None:
    *_, error, failed = run.stream
    assert error["type"] == "error"
    assert (error["code"], error["message"]) == (code, message)
    assert failed["type"] == "response.failed"
    assert run.body["status"] == "failed"
    assert run.body["error"] == {"code": code, "message": message}


async def test_raises_in_message():
    run = await run_response(raises_in_message)

    assert "response.output_text.done" not in run.types
    assert "response.content_part.done" not in run.types
    assert "response.output_item.done" not in run.types
    assert "response.completed" not in run.types
    _assert_failed(run, "server_error", INTERNAL_ERROR_MESSAGE)

    [message] = run.body["output"]
    assert message["status"] == "in_progress"
    assert message["content"] == [
        {
            "type": "output_text",
            "text": "Partial",
            "annotations": [],
            "logprobs": [],
        }
    ]


async def test_raises_with_open_items():
    run = await run_response(raises_with_open_items)

    done = [e for e in run.types if e.endswith(".done")]
    assert done == ["response.output_item.done"]
    [web_search_done] = [
        e for e in run.stream if e["type"] == "response.output_item.done"
    ]
    assert web_search_done["item"]["type"] == "web_search_call"
    assert web_search_done["item"]["status"] == "failed"
    assert "response.web_search_call.completed" not in run.types
    _assert_failed(run, "server_error", INTERNAL_ERROR_MESSAGE)

    message, web_search, function_call = run.body["output"]
    assert message["status"] == "in_progress"
    assert web_search["status"] == "failed"
    assert function_call["status"] == "in_progress"
    assert function_call["arguments"] == '{"a":'


async def _raises_in_reasoning(request: Request, response: Response) -> None:
    with response.create_reasoning() as reasoning:
        reasoning.append_summary("Thinking")
        raise _Boom()


async def _raises_in_refusal(request: Request, response: Response) -> None:
    with response.create_message() as message:
        message.append_refusal("No")
        raise _Boom()


async def _raises_in_function_call(
    request: Request, response: Response
) -> None:
    with response.create_function_call("f") as call:
        call.append_arguments("{")
        raise _Boom()


async def _raises_in_custom_tool_call(
    request: Request, response: Response
) -> None:
    with response.create_custom_tool_call("c") as call:
        call.append_input("SELECT")
        raise _Boom()


@pytest.mark.parametrize(
    "producer",
    [
        _raises_in_reasoning,
        _raises_in_refusal,
        _raises_in_function_call,
        _raises_in_custom_tool_call,
    ],
)
async def test_propagate_builders_emit_no_done(producer):
    # No `.done` of any kind, the item stays in progress
    run = await run_response(producer)

    assert [t for t in run.types if t.endswith(".done")] == []
    _assert_failed(run, "server_error", INTERNAL_ERROR_MESSAGE)
    [item] = run.body["output"]
    assert item.get("status", "in_progress") == "in_progress"


async def _raises_in_web_search(request: Request, response: Response) -> None:
    with response.create_web_search() as search:
        search.searching(query="q")
        raise _Boom()


async def _raises_in_image_generation(
    request: Request, response: Response
) -> None:
    with response.create_image_generation() as image:
        image.generating()
        raise _Boom()


@pytest.mark.parametrize(
    "producer, completed",
    [
        (_raises_in_web_search, "response.web_search_call.completed"),
        (
            _raises_in_image_generation,
            "response.image_generation_call.completed",
        ),
    ],
)
async def test_raises_in_server_tool(producer, completed: str):
    run = await run_response(producer)

    assert completed not in run.types
    item_done, error, failed = run.stream[-3:]
    assert item_done["type"] == "response.output_item.done"
    assert item_done["item"]["status"] == "failed"
    assert error["type"] == "error"
    assert failed["type"] == "response.failed"
    _assert_failed(run, "server_error", INTERNAL_ERROR_MESSAGE)


@pytest.mark.parametrize(
    "exc, code, message",
    [
        (
            DIALException("Slow down", status_code=429),
            "rate_limit_exceeded",
            "Slow down",
        ),
        (DIALException("Bad", status_code=400), "invalid_prompt", "Bad"),
        (DIALException("Down", status_code=503), "server_error", "Down"),
        (_Boom("secret"), "server_error", INTERNAL_ERROR_MESSAGE),
    ],
)
async def test_exception_is_mapped(exc: Exception, code: str, message: str):
    async def producer(request: Request, response: Response) -> None:
        response.append_text("Hi")
        raise exc

    run = await run_response(producer)

    _assert_failed(run, code, message)
    assert "secret" not in run.transcript
    # Kept as raised, for the transport's HTTP error
    assert run.exception is not None
    if isinstance(exc, DIALException):
        assert run.exception is exc
    else:
        assert isinstance(run.exception, InternalServerError)
        assert run.exception.message == INTERNAL_ERROR_MESSAGE


async def test_raises_before_any_event():
    # What the transport sees, and answers with an HTTP error instead
    async def producer(request: Request, response: Response) -> None:
        raise _Boom()

    run = await run_response(producer)

    assert run.types == [
        "response.created",
        "response.in_progress",
        "error",
        "response.failed",
    ]
    assert isinstance(run.exception, InternalServerError)


async def test_dial_exception_keeps_its_status_code():
    # What the transport needs for an HTTP 429 rather than a failed stream
    async def producer(request: Request, response: Response) -> None:
        raise DIALException("Slow down", status_code=429)

    run = await run_response(producer)

    assert run.exception is not None
    assert run.exception.status_code == 429


async def test_non_dial_exception_is_logged(caplog):
    async def producer(request: Request, response: Response) -> None:
        raise _Boom("secret")

    with caplog.at_level(logging.ERROR):
        await run_response(producer)

    assert "secret" in caplog.text


async def _fails_in_message(request: Request, response: Response) -> None:
    with response.create_message() as message:
        message.append_text("Partial")
        response.fail(ErrorCode.IMAGE_TOO_LARGE, "The image is too large")


async def test_fail():
    run = await run_response(_fails_in_message)

    assert [t for t in run.types if t.endswith(".done")] == []
    assert "response.completed" not in run.types
    _assert_failed(run, "image_too_large", "The image is too large")
    # Deliberate, not raised: the transport streams it
    assert run.exception is None
    [message] = run.body["output"]
    assert message["status"] == "in_progress"
    assert message["content"][0]["text"] == "Partial"


@pytest.mark.parametrize("stream", [True, False])
async def test_fail_leaves_the_block_open_on_exit(stream: bool):
    # Not only on the wire: the response object isn't tidied up either
    response = make_response(stream=stream)

    await response._run_producer(_fails_in_message)

    message = response.items[0]
    assert not message.closed
    assert message._item is response._ctx.response_object.output[0]
    assert message._item.status == "in_progress"


async def test_fail_closes_an_open_server_tool_as_failed():
    async def producer(request: Request, response: Response) -> None:
        response.create_image_generation().generating()
        response.fail(ErrorCode.IMAGE_PARSE_ERROR, "Unreadable")

    run = await run_response(producer)

    assert run.types[-3:] == [
        "response.output_item.done",
        "error",
        "response.failed",
    ]
    assert run.body["output"][0]["status"] == "failed"
    assert "response.image_generation_call.completed" not in run.types


async def test_fail_takes_a_string_code():
    async def producer(request: Request, response: Response) -> None:
        response.fail("server_error", "Down")  # type: ignore

    run = await run_response(producer)

    _assert_failed(run, "server_error", "Down")


_WRITES_AFTER_END: list[tuple[Callable[[Response, Any], Any], str]] = [
    (
        lambda response, _: response.fail(ErrorCode.SERVER_ERROR, "Again"),
        "Trying to fail the response after end of generation",
    ),
    (
        lambda response, _: response.error(ErrorCode.SERVER_ERROR, "Again"),
        "Trying to emit an error after end of generation",
    ),
    (
        lambda response, _: response.unsafe_emit({"type": "x"}),
        "Trying to emit an event after end of generation",
    ),
    (
        lambda response, _: response.set_usage(1, 1),
        'Trying to set "usage" after end of generation',
    ),
    (
        lambda response, _: response.set_incomplete("content_filter"),
        "Trying to set the response incomplete after end of generation",
    ),
    (
        lambda response, _: response.create_reasoning(),
        "Trying to create an item after end of generation",
    ),
    (
        lambda response, _: response.append_text("a"),
        "Trying to append text to a message after end of generation",
    ),
    (
        lambda _, message: message.create_text(),
        "Trying to create a text part in a message after end of generation",
    ),
    (
        lambda _, message: message.close(),
        "Trying to close a message after end of generation",
    ),
]


@pytest.mark.parametrize("stream", [True, False])
@pytest.mark.parametrize("write, reason", _WRITES_AFTER_END)
def test_nothing_is_written_after_fail(
    caplog, stream: bool, write: Callable[[Response, Any], Any], reason: str
):
    response = make_response(stream=stream)
    message = response.create_message()
    response.append_text("Hi")
    response.fail(ErrorCode.SERVER_ERROR, "Down")
    output = _dump(response._ctx.response_object)["output"]
    body = response._body

    with raises_runtime_error(caplog, reason):
        write(response, message)

    assert _dump(response._ctx.response_object)["output"] == output
    assert response._body == body
    assert not message.closed


async def test_a_write_after_fail_does_not_change_the_failure(caplog):
    async def producer(request: Request, response: Response) -> None:
        response.fail(ErrorCode.SERVER_ERROR, "Down")
        response.append_text("Late")

    with caplog.at_level(logging.ERROR):
        run = await run_response(producer)

    assert run.types == [
        "response.created",
        "response.in_progress",
        "error",
        "response.failed",
    ]
    _assert_failed(run, "server_error", "Down")
    assert "after end of generation" in caplog.text


async def test_exception_after_fail(caplog):
    async def producer(request: Request, response: Response) -> None:
        response.fail(ErrorCode.SERVER_ERROR, "Down")
        raise _Boom("late")

    with caplog.at_level(logging.ERROR):
        run = await run_response(producer)

    assert run.types[-2:] == ["error", "response.failed"]
    _assert_failed(run, "server_error", "Down")
    assert "late" in caplog.text
    # The failure was the handler's own, already sent
    assert run.exception is None


async def test_error_is_not_terminal():
    async def producer(request: Request, response: Response) -> None:
        response.append_text("Hi")
        response.error(ErrorCode.INVALID_PROMPT, "Odd", param="input")
        response.append_text(" there")

    run = await run_response(producer)

    [error] = [e for e in run.stream if e["type"] == "error"]
    assert error["code"] == "invalid_prompt"
    assert error["message"] == "Odd"
    assert error["param"] == "input"
    assert run.types[-1] == "response.completed"
    assert run.body["error"] is None
    assert run.body["output"][0]["content"][0]["text"] == "Hi there"


@pytest.mark.parametrize("raises", [False, True])
async def test_failed_response_carries_the_usage(raises: bool):
    async def producer(request: Request, response: Response) -> None:
        response.set_usage(10, 5)
        response.append_text("Partial")
        if raises:
            raise _Boom()
        response.fail(ErrorCode.SERVER_ERROR, "Down")

    run = await run_response(producer)

    assert run.types[-1] == "response.failed"
    assert run.body["usage"]["total_tokens"] == 15


def test_error_in_block_mode_is_dropped_with_a_warning(caplog):
    response = make_response(stream=False)

    with caplog.at_level(logging.WARNING):
        response.error(ErrorCode.SERVER_ERROR, "Odd")

    assert "The error event is dropped" in caplog.text
    assert response._ctx._queue.empty()
