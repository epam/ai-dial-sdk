import json
from collections.abc import AsyncIterator

from aidial_sdk.responses import events
from aidial_sdk.responses.enums import ItemStatus, ResponseStatus
from aidial_sdk.responses.events import Event, to_sse_response
from aidial_sdk.responses.models import (
    ResponseObject,
    ResponseOutputMessage,
    ResponseOutputText,
)
from tests.responses.conftest import validate_event

_IDX = {"item_id": "msg_1", "output_index": 0, "content_index": 0}


async def _stream(*items: Event | str) -> AsyncIterator[Event | str]:
    for item in items:
        yield item


async def _frames(*items: Event | str) -> list[str]:
    return [frame async for frame in to_sse_response(_stream(*items))]


def _numbered(*evts: Event) -> list[Event]:
    for number, event in enumerate(evts):
        event["sequence_number"] = number
    return list(evts)


async def test_frame_bytes():
    event = events.output_text_delta(**_IDX, delta="Hello", logprobs=[])
    event["sequence_number"] = 6

    assert await _frames(event) == [
        "event: response.output_text.delta\n"
        'data: {"type":"response.output_text.delta","sequence_number":6,'
        '"item_id":"msg_1","output_index":0,"content_index":0,'
        '"delta":"Hello","logprobs":[]}\n'
        "\n"
    ]


async def test_heartbeat_is_passed_through():
    event = _numbered(
        events.web_search_call_searching(item_id="ws_1", output_index=0)
    )[0]

    frames = await _frames(": heartbeat\n\n", event, ": heartbeat\n\n")

    assert frames[0] == frames[2] == ": heartbeat\n\n"
    assert frames[1].startswith("event: response.web_search_call.searching\n")


async def test_lifecycle_stream_has_no_done_marker():
    response_object = ResponseObject(
        id="resp_1", created_at=1700000000, model="m"
    )
    message = ResponseOutputMessage(id="msg_1")
    text = ResponseOutputText()

    stream = [events.response_created(response=response_object)]
    stream.append(events.response_in_progress(response=response_object))
    stream.append(events.output_item_added(output_index=0, item=message))
    message.content.append(text)
    stream.append(events.content_part_added(**_IDX, part=text))
    text.text = "Hello"
    stream.append(events.output_text_delta(**_IDX, delta="Hello", logprobs=[]))
    stream.append(events.output_text_done(**_IDX, text="Hello", logprobs=[]))
    stream.append(events.content_part_done(**_IDX, part=text))
    message.status = ItemStatus.COMPLETED
    stream.append(events.output_item_done(output_index=0, item=message))
    response_object.output.append(message)
    response_object.status = ResponseStatus.COMPLETED
    stream.append(events.response_completed(response=response_object))

    frames = await _frames(*_numbered(*stream))
    body = "".join(frames)

    assert "[DONE]" not in body
    assert frames[-1].startswith("event: response.completed\n")

    for frame, event in zip(frames, stream, strict=True):
        name_line, data_line, blank = frame.split("\n", 2)
        assert blank == "\n"
        assert name_line == f"event: {event['type']}"
        assert data_line.startswith("data: ")

        data = json.loads(data_line.removeprefix("data: "))
        assert data == event
        validate_event(data)
