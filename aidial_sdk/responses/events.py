"""
The wire seam: the only module that knows the Responses wire format.

Each constructor returns a plain `dict` for one of the 32 event types
the builders produce. Models are serialised at construction time,
so an event never holds a reference to the live response object:
otherwise `response.created` would serialise whatever state the response
object reaches by the time the event is written.

`sequence_number` is a `None` placeholder that the response context
fills in when the event is emitted.

`hold_back_preamble` withholds the lifecycle preamble until it's known
whether a stream is opened at all, and `to_sse_response` frames the events
for the wire.
"""

import json
from collections.abc import AsyncIterator
from enum import Enum
from typing import Any

from aidial_sdk._pydantic._compat import BaseModel
from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.responses.enums import ErrorCode
from aidial_sdk.responses.models import (
    Annotation,
    ContentPart,
    Logprob,
    ReasoningSummary,
    ResponseObject,
    ResponseOutputItem,
)

Event = dict[str, Any]


def _event(type: str, **fields: Any) -> Event:
    return {"type": type, "sequence_number": None, **fields}


def _plain(data: Any) -> Any:
    # On the pydantic v1 path `model_dump(mode="json")` keeps enum members
    if isinstance(data, Enum):
        return data.value
    if isinstance(data, dict):
        return {key: _plain(value) for key, value in data.items()}
    if isinstance(data, list):
        return [_plain(value) for value in data]
    return data


def _dump(model: BaseModel) -> dict[str, Any]:
    return _plain(model.model_dump(mode="json"))


def _dump_logprobs(logprobs: list[Logprob]) -> list[dict[str, Any]]:
    # The logprobs of the text events have no `bytes`,
    # unlike the ones of the `output_text` content part
    return [
        {
            "token": logprob.token,
            "logprob": logprob.logprob,
            "top_logprobs": [
                {"token": top.token, "logprob": top.logprob}
                for top in logprob.top_logprobs
            ],
        }
        for logprob in logprobs
    ]


# lifecycle


def response_created(*, response: ResponseObject) -> Event:
    return _event("response.created", response=_dump(response))


def response_in_progress(*, response: ResponseObject) -> Event:
    return _event("response.in_progress", response=_dump(response))


def response_completed(*, response: ResponseObject) -> Event:
    return _event("response.completed", response=_dump(response))


def response_incomplete(*, response: ResponseObject) -> Event:
    return _event("response.incomplete", response=_dump(response))


def response_failed(*, response: ResponseObject) -> Event:
    return _event("response.failed", response=_dump(response))


# error


def error(*, code: ErrorCode, message: str, param: str | None = None) -> Event:
    return _event("error", code=code.value, message=message, param=param)


# item


def output_item_added(*, output_index: int, item: ResponseOutputItem) -> Event:
    return _event(
        "response.output_item.added",
        output_index=output_index,
        item=_dump(item),
    )


def output_item_done(*, output_index: int, item: ResponseOutputItem) -> Event:
    return _event(
        "response.output_item.done",
        output_index=output_index,
        item=_dump(item),
    )


# part


def content_part_added(
    *,
    item_id: str,
    output_index: int,
    content_index: int,
    part: ContentPart,
) -> Event:
    return _event(
        "response.content_part.added",
        item_id=item_id,
        output_index=output_index,
        content_index=content_index,
        part=_dump(part),
    )


def content_part_done(
    *,
    item_id: str,
    output_index: int,
    content_index: int,
    part: ContentPart,
) -> Event:
    return _event(
        "response.content_part.done",
        item_id=item_id,
        output_index=output_index,
        content_index=content_index,
        part=_dump(part),
    )


# text


def output_text_delta(
    *,
    item_id: str,
    output_index: int,
    content_index: int,
    delta: str,
    logprobs: list[Logprob],
) -> Event:
    return _event(
        "response.output_text.delta",
        item_id=item_id,
        output_index=output_index,
        content_index=content_index,
        delta=delta,
        logprobs=_dump_logprobs(logprobs),
    )


def output_text_done(
    *,
    item_id: str,
    output_index: int,
    content_index: int,
    text: str,
    logprobs: list[Logprob],
) -> Event:
    return _event(
        "response.output_text.done",
        item_id=item_id,
        output_index=output_index,
        content_index=content_index,
        text=text,
        logprobs=_dump_logprobs(logprobs),
    )


def output_text_annotation_added(
    *,
    item_id: str,
    output_index: int,
    content_index: int,
    annotation_index: int,
    annotation: Annotation,
) -> Event:
    return _event(
        "response.output_text.annotation.added",
        item_id=item_id,
        output_index=output_index,
        content_index=content_index,
        annotation_index=annotation_index,
        annotation=_dump(annotation),
    )


# refusal


def refusal_delta(
    *, item_id: str, output_index: int, content_index: int, delta: str
) -> Event:
    return _event(
        "response.refusal.delta",
        item_id=item_id,
        output_index=output_index,
        content_index=content_index,
        delta=delta,
    )


def refusal_done(
    *, item_id: str, output_index: int, content_index: int, refusal: str
) -> Event:
    return _event(
        "response.refusal.done",
        item_id=item_id,
        output_index=output_index,
        content_index=content_index,
        refusal=refusal,
    )


# summary


def reasoning_summary_part_added(
    *,
    item_id: str,
    output_index: int,
    summary_index: int,
    part: ReasoningSummary,
) -> Event:
    return _event(
        "response.reasoning_summary_part.added",
        item_id=item_id,
        output_index=output_index,
        summary_index=summary_index,
        part=_dump(part),
    )


def reasoning_summary_text_delta(
    *, item_id: str, output_index: int, summary_index: int, delta: str
) -> Event:
    return _event(
        "response.reasoning_summary_text.delta",
        item_id=item_id,
        output_index=output_index,
        summary_index=summary_index,
        delta=delta,
    )


def reasoning_summary_text_done(
    *, item_id: str, output_index: int, summary_index: int, text: str
) -> Event:
    return _event(
        "response.reasoning_summary_text.done",
        item_id=item_id,
        output_index=output_index,
        summary_index=summary_index,
        text=text,
    )


def reasoning_summary_part_done(
    *,
    item_id: str,
    output_index: int,
    summary_index: int,
    part: ReasoningSummary,
    incomplete: bool = False,
) -> Event:
    # The only part-level status in the protocol,
    # omitted when the part completed normally
    return _event(
        "response.reasoning_summary_part.done",
        item_id=item_id,
        output_index=output_index,
        summary_index=summary_index,
        part=_dump(part),
        **({"status": "incomplete"} if incomplete else {}),
    )


# reasoning


def reasoning_text_delta(
    *, item_id: str, output_index: int, content_index: int, delta: str
) -> Event:
    return _event(
        "response.reasoning_text.delta",
        item_id=item_id,
        output_index=output_index,
        content_index=content_index,
        delta=delta,
    )


def reasoning_text_done(
    *, item_id: str, output_index: int, content_index: int, text: str
) -> Event:
    return _event(
        "response.reasoning_text.done",
        item_id=item_id,
        output_index=output_index,
        content_index=content_index,
        text=text,
    )


# function


def function_call_arguments_delta(
    *, item_id: str, output_index: int, delta: str
) -> Event:
    return _event(
        "response.function_call_arguments.delta",
        item_id=item_id,
        output_index=output_index,
        delta=delta,
    )


def function_call_arguments_done(
    *, item_id: str, output_index: int, name: str, arguments: str
) -> Event:
    return _event(
        "response.function_call_arguments.done",
        item_id=item_id,
        output_index=output_index,
        name=name,
        arguments=arguments,
    )


# custom tool


def custom_tool_call_input_delta(
    *, item_id: str, output_index: int, delta: str
) -> Event:
    return _event(
        "response.custom_tool_call_input.delta",
        item_id=item_id,
        output_index=output_index,
        delta=delta,
    )


def custom_tool_call_input_done(
    *, item_id: str, output_index: int, input: str
) -> Event:
    return _event(
        "response.custom_tool_call_input.done",
        item_id=item_id,
        output_index=output_index,
        input=input,
    )


# web search


def web_search_call_in_progress(*, item_id: str, output_index: int) -> Event:
    return _event(
        "response.web_search_call.in_progress",
        item_id=item_id,
        output_index=output_index,
    )


def web_search_call_searching(*, item_id: str, output_index: int) -> Event:
    return _event(
        "response.web_search_call.searching",
        item_id=item_id,
        output_index=output_index,
    )


def web_search_call_completed(*, item_id: str, output_index: int) -> Event:
    return _event(
        "response.web_search_call.completed",
        item_id=item_id,
        output_index=output_index,
    )


# image generation


def image_generation_call_in_progress(
    *, item_id: str, output_index: int
) -> Event:
    return _event(
        "response.image_generation_call.in_progress",
        item_id=item_id,
        output_index=output_index,
    )


def image_generation_call_generating(
    *, item_id: str, output_index: int
) -> Event:
    return _event(
        "response.image_generation_call.generating",
        item_id=item_id,
        output_index=output_index,
    )


def image_generation_call_partial_image(
    *,
    item_id: str,
    output_index: int,
    partial_image_index: int,
    partial_image_b64: str,
) -> Event:
    return _event(
        "response.image_generation_call.partial_image",
        item_id=item_id,
        output_index=output_index,
        partial_image_index=partial_image_index,
        partial_image_b64=partial_image_b64,
    )


def image_generation_call_completed(
    *, item_id: str, output_index: int
) -> Event:
    return _event(
        "response.image_generation_call.completed",
        item_id=item_id,
        output_index=output_index,
    )


# SSE framing


def _format_event(event: Event) -> str:
    data = json.dumps(event, separators=(",", ":"))
    return f"event: {event['type']}\ndata: {data}\n\n"


async def to_sse_response(
    stream: AsyncIterator[Event | str],
) -> AsyncIterator[str]:
    """
    Frames each event as a named SSE message whose `data` repeats the name
    in `type`. Strings, i.e. heartbeat comments, are passed through as is.

    Unlike chat completion, the stream doesn't end with `data: [DONE]`:
    the terminal `response.*` event is the terminator.
    """
    async for event in stream:
        yield event if isinstance(event, str) else _format_event(event)


_PREAMBLE = {"response.created", "response.in_progress"}


async def hold_back_preamble(
    stream: AsyncIterator[Event | DIALException | str],
) -> AsyncIterator[Event | str]:
    """
    Withholds `response.created` and `response.in_progress` until what
    follows them is known.

    An exception right after them is one the handler raised before
    producing any event. Nothing has reached the client, so it's raised as
    an ordinary HTTP error and no stream is opened.

    Anything else, a heartbeat included, opens the stream. An exception
    is then dropped: its failure events follow it.
    """
    held: list[Event | str] = []
    while True:
        item = await stream.__anext__()
        if isinstance(item, DIALException):
            raise item.to_fastapi_exception()

        held.append(item)
        if isinstance(item, str) or item["type"] not in _PREAMBLE:
            break

    async def _generator() -> AsyncIterator[Event | str]:
        for item in held:
            yield item

        async for item in stream:
            if not isinstance(item, DIALException):
                yield item

    return _generator()
