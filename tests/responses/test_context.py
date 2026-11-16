import re

from aidial_sdk.responses import events
from aidial_sdk.responses._context import _ResponseContext
from aidial_sdk.responses._ids import MESSAGE_PREFIX
from aidial_sdk.responses.enums import ErrorCode
from aidial_sdk.responses.events import Event
from aidial_sdk.responses.models import ResponseObject, ResponseOutputMessage
from tests.responses.conftest import validate_event

_IDX = {"item_id": "msg_1", "output_index": 0}


def _context(*, stream: bool) -> _ResponseContext:
    response_object = ResponseObject(
        id="resp_1", created_at=1700000000, model="m"
    )
    return _ResponseContext(response_object, stream=stream)


def _events(ctx: _ResponseContext) -> list[Event]:
    return [
        events.response_created(response=ctx.response_object),
        events.response_in_progress(response=ctx.response_object),
        events.output_item_added(
            output_index=0, item=ResponseOutputMessage(id="msg_1")
        ),
        events.refusal_delta(**_IDX, content_index=0, delta="No"),
        events.error(code=ErrorCode.SERVER_ERROR, message="Boom"),
    ]


def _drain(ctx: _ResponseContext) -> list[Event]:
    drained = []
    while not ctx._queue.empty():
        drained.append(ctx._queue.get_nowait())
    return drained


def test_emit_assigns_gapless_sequence_numbers():
    ctx = _context(stream=True)
    emitted = _events(ctx)

    for event in emitted:
        ctx.emit(event)

    queued = _drain(ctx)

    assert [e["sequence_number"] for e in queued] == list(range(len(emitted)))
    assert all(q is e for q, e in zip(queued, emitted, strict=True))
    for event in queued:
        validate_event(event)


def test_emit_is_a_no_op_in_block_mode():
    ctx = _context(stream=False)
    emitted = _events(ctx)

    for event in emitted:
        ctx.emit(event)

    assert ctx._queue.empty()
    assert ctx._sequence_number == 0
    assert all(e["sequence_number"] is None for e in emitted)


def test_next_output_index():
    ctx = _context(stream=True)

    assert [ctx.next_output_index() for _ in range(3)] == [0, 1, 2]


def test_new_id():
    ctx = _context(stream=True)
    ids = {ctx.new_id(MESSAGE_PREFIX) for _ in range(3)}

    assert len(ids) == 3
    assert all(re.fullmatch(r"msg_[0-9a-f]{32}", i) for i in ids)


def test_start_generation_emits_the_preamble_once():
    ctx = _context(stream=True)

    ctx.start_generation()
    ctx.start_generation()

    queued = _drain(ctx)
    assert [e["type"] for e in queued] == [
        "response.created",
        "response.in_progress",
    ]
    assert ctx.generation_started
    for event in queued:
        validate_event(event)


def test_start_generation_in_block_mode():
    # The guard rails that depend on it must not differ between the modes
    ctx = _context(stream=False)

    ctx.start_generation()

    assert ctx.generation_started
    assert ctx._queue.empty()


def test_nothing_is_emitted_after_finish():
    ctx = _context(stream=True)
    ctx.start_generation()

    ctx.finish(events.response_completed(response=ctx.response_object))
    ctx.emit(events.error(code=ErrorCode.SERVER_ERROR, message="Late"))

    assert [e["type"] for e in _drain(ctx)] == [
        "response.created",
        "response.in_progress",
        "response.completed",
    ]
