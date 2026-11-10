import asyncio
from collections.abc import AsyncIterator

import pytest
from fastapi import HTTPException as FastAPIException

from aidial_sdk._errors import INTERNAL_ERROR_MESSAGE
from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.exceptions import (
    InternalServerError,
    InvalidRequestError,
    RuntimeServerError,
)
from aidial_sdk.responses import events
from aidial_sdk.responses.enums import ErrorCode
from aidial_sdk.responses.events import Event, hold_back_preamble
from aidial_sdk.responses.models import ResponseObject
from aidial_sdk.responses.request import Request
from aidial_sdk.responses.response import Response
from tests.responses.conftest import ROUTES, Handler, Route, run_handler


def _stream_types(handler: Handler) -> list[str]:
    run = run_handler(handler, stream=True)
    assert run.http.status_code == 200
    assert run.http.headers["content-type"].startswith("text/event-stream")
    assert run.comments == []
    return run.types


class _Boom(Exception):
    pass


async def _raise_at_once(request: Request, response: Response) -> None:
    raise _Boom("secret")


async def _raise_after_await(request: Request, response: Response) -> None:
    await asyncio.sleep(0.01)
    raise _Boom("secret")


async def _raise_after_setters(request: Request, response: Response) -> None:
    # Neither produces an event, so generation hasn't started
    response.set_response_id("resp_x").set_model("x").set_usage(1, 1)
    response.append_header("X-Upstream", "1")
    raise _Boom("secret")


async def _raise_dial(request: Request, response: Response) -> None:
    raise InvalidRequestError("Bad input", param="input")


@ROUTES
@pytest.mark.parametrize("stream", [True, False])
@pytest.mark.parametrize(
    "handler, exception",
    [
        (_raise_at_once, InternalServerError(INTERNAL_ERROR_MESSAGE)),
        (_raise_after_await, InternalServerError(INTERNAL_ERROR_MESSAGE)),
        (_raise_after_setters, InternalServerError(INTERNAL_ERROR_MESSAGE)),
        (_raise_dial, InvalidRequestError("Bad input", param="input")),
    ],
)
def test_early_exception_is_an_http_error(
    route: Route, stream: bool, handler: Handler, exception: DIALException
):
    """DIAL's error envelope, and no SSE stream at all."""
    response = run_handler(handler, stream=stream, route=route).http

    assert response.status_code == exception.status_code
    assert response.headers["content-type"] == "application/json"
    assert response.json() == exception.json_error()
    assert "event:" not in response.text
    assert "secret" not in response.text


@ROUTES
def test_block_exception_after_events_is_an_http_error(route: Route):
    # In block mode nothing has reached the client whatever was produced
    async def handler(request: Request, response: Response) -> None:
        with response.create_message() as message:
            message.append_text("Partial")
            raise _Boom()

    response = run_handler(handler, stream=False, route=route).http

    assert response.status_code == 500
    assert (
        response.json()
        == InternalServerError(INTERNAL_ERROR_MESSAGE).json_error()
    )


async def _produce(request: Request, response: Response) -> None:
    await asyncio.sleep(0.01)
    with response.create_message() as message:
        message.append_text("Hi")


async def _produce_nothing(request: Request, response: Response) -> None:
    pass


async def _raise_after_item(request: Request, response: Response) -> None:
    response.create_message()
    raise _Boom()


async def _raise_after_error(request: Request, response: Response) -> None:
    # The handler's own `error` is its first event: the stream has started
    response.error(ErrorCode.SERVER_ERROR, "Odd")
    raise _Boom()


async def _raise_after_unsafe_emit(
    request: Request, response: Response
) -> None:
    response.unsafe_emit(
        events.web_search_call_searching(item_id="ws_x", output_index=0)
    )
    raise _Boom()


async def _fail(request: Request, response: Response) -> None:
    # The same events as an early exception, but the handler's own
    response.fail(ErrorCode.SERVER_ERROR, "Down")


_PREAMBLE = ["response.created", "response.in_progress"]
_FAILURE = ["error", "response.failed"]


@pytest.mark.parametrize(
    "handler, types",
    [
        (
            _produce,
            [
                *_PREAMBLE,
                "response.output_item.added",
                "response.content_part.added",
                "response.output_text.delta",
                "response.output_text.done",
                "response.content_part.done",
                "response.output_item.done",
                "response.completed",
            ],
        ),
        (_produce_nothing, [*_PREAMBLE, "response.completed"]),
        (
            _raise_after_item,
            [*_PREAMBLE, "response.output_item.added", *_FAILURE],
        ),
        (_raise_after_error, [*_PREAMBLE, "error", *_FAILURE]),
        (
            _raise_after_unsafe_emit,
            [*_PREAMBLE, "response.web_search_call.searching", *_FAILURE],
        ),
        (_fail, [*_PREAMBLE, *_FAILURE]),
    ],
)
def test_stream_opens_with_the_preamble(handler: Handler, types: list[str]):
    assert _stream_types(handler) == types


def test_fail_in_block_mode_is_a_failed_response():
    run = run_handler(_fail, stream=False)

    assert run.http.status_code == 200
    assert run.body is not None
    assert run.body["status"] == "failed"
    assert run.body["error"] == {
        "code": "server_error",
        "message": "Down",
    }


def test_header_reaches_the_stream():
    # The stream opens once the handler has produced its first event
    async def handler(request: Request, response: Response) -> None:
        await asyncio.sleep(0.01)
        response.append_header("X-Upstream", "1")
        response.append_text("Hi")

    response = run_handler(handler, stream=True).http

    assert response.status_code == 200
    assert response.headers["X-Upstream"] == "1"


def test_heartbeat_opens_the_stream():
    # A heartbeat reached the client, so an HTTP error is too late:
    # the exception is reported in the stream, as in chat completion
    async def handler(request: Request, response: Response) -> None:
        await asyncio.sleep(0.3)
        raise _Boom()

    run = run_handler(handler, stream=True, heartbeat_interval=0.05)

    assert run.http.status_code == 200
    assert run.http.text.startswith(": heartbeat\n\n")
    assert set(run.comments) == {": heartbeat"}
    assert run.types == [*_PREAMBLE, *_FAILURE]


def _preamble() -> list[Event]:
    response_object = ResponseObject(id="resp_1", created_at=0, model="m")
    return [
        events.response_created(response=response_object),
        events.response_in_progress(response=response_object),
    ]


async def _items(
    *items: Event | DIALException | str,
) -> AsyncIterator[Event | DIALException | str]:
    for item in items:
        yield item


async def test_hold_back_raises_an_exception_after_the_preamble():
    exception = InvalidRequestError("Bad input")

    with pytest.raises(FastAPIException) as exc_info:
        await hold_back_preamble(_items(*_preamble(), exception))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == exception.json_error()


async def test_hold_back_drops_an_exception_once_the_stream_opened():
    error = events.error(code=ErrorCode.SERVER_ERROR, message="Down")
    stream = _items(
        ": heartbeat\n\n", *_preamble(), RuntimeServerError("x"), error
    )

    held = await hold_back_preamble(stream)

    assert [item async for item in held] == [
        ": heartbeat\n\n",
        *_preamble(),
        error,
    ]
