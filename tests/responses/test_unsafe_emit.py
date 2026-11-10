import logging

from openai.types.responses import (
    ResponseErrorEvent,
    ResponseMcpCallInProgressEvent,
)

from aidial_sdk.responses.events import _dump
from tests.responses.conftest import (
    _parse,
    drain,
    make_response,
    validate_event,
)

_RAW = {
    "type": "response.output_text.delta",
    "sequence_number": 42,
    "item_id": "msg_upstream",
    "output_index": 7,
    "content_index": 0,
    "delta": "Hi",
    "logprobs": [],
}


def test_raw_event_reaches_the_stream_verbatim():
    response = make_response(stream=True)

    response.unsafe_emit(_RAW)

    created, in_progress, raw = drain(response._ctx)
    assert (created["type"], in_progress["type"]) == (
        "response.created",
        "response.in_progress",
    )
    assert raw == {**_RAW, "sequence_number": 2}
    # The caller's event is left alone
    assert _RAW["sequence_number"] == 42


def test_raw_event_bypasses_the_response_object():
    response = make_response(stream=True)
    before = _dump(response._ctx.response_object)

    response.unsafe_emit(
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {
                "type": "message",
                "id": "msg_x",
                "role": "assistant",
                "status": "in_progress",
                "content": [],
            },
        }
    )

    assert _dump(response._ctx.response_object) == before
    assert response.items == ()


def test_out_of_scope_event_round_trips():
    # An event type with no builder: reachable only through the escape hatch
    response = make_response(stream=True)
    event = ResponseMcpCallInProgressEvent(
        type="response.mcp_call.in_progress",
        item_id="mcp_1",
        output_index=0,
        sequence_number=0,
    )

    response.unsafe_emit(event)

    *_, raw = drain(response._ctx)
    validate_event(raw)
    assert raw == {
        "type": "response.mcp_call.in_progress",
        "item_id": "mcp_1",
        "output_index": 0,
        "sequence_number": 2,
    }


def test_model_is_dumped_without_unset_fields():
    response = make_response(stream=True)
    response.create_message()
    drain(response._ctx)

    # `code` and `param` are optional and left unset. `_parse` rather than
    # `model_validate`, which openai's models lack on an installed pydantic v1
    response.unsafe_emit(
        _parse(
            ResponseErrorEvent,
            {"type": "error", "message": "Down", "sequence_number": 9},
        )
    )

    [raw] = drain(response._ctx)
    assert raw == {"type": "error", "message": "Down", "sequence_number": 3}


def test_block_mode_is_a_no_op_that_logs(caplog):
    response = make_response(stream=False)
    before = _dump(response._ctx.response_object)

    with caplog.at_level(logging.WARNING):
        response.unsafe_emit(_RAW)

    assert "unsafe_emit" in caplog.text
    assert response._ctx._queue.empty()
    assert _dump(response._ctx.response_object) == before


def test_sequence_numbers_stay_gapless_around_raw_events():
    response = make_response(stream=True)

    response.append_text("a")
    response.unsafe_emit(_RAW)
    response.append_text("b")

    stream = drain(response._ctx)
    assert [e["sequence_number"] for e in stream] == list(range(len(stream)))
