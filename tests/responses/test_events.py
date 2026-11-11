import copy
from collections.abc import Callable
from enum import Enum
from typing import Any, get_args

import pytest
from openai.types.responses import ResponseStreamEvent
from openai.types.responses import response_output_text as openai_text

from aidial_sdk.responses import events
from aidial_sdk.responses.enums import (
    ErrorCode,
    IncompleteReason,
    ItemStatus,
    MessagePhase,
    ResponseStatus,
)
from aidial_sdk.responses.events import Event
from aidial_sdk.responses.models import (
    ImageGenerationCall,
    IncompleteDetails,
    InputTokensDetails,
    Logprob,
    LogprobTopLogprob,
    OutputTokensDetails,
    ReasoningContent,
    ReasoningSummary,
    ResponseCustomToolCall,
    ResponseError,
    ResponseFunctionToolCall,
    ResponseFunctionWebSearch,
    ResponseObject,
    ResponseOutputItem,
    ResponseOutputMessage,
    ResponseOutputRefusal,
    ResponseOutputText,
    ResponseReasoningItem,
    SearchAction,
    SearchSource,
    UrlCitation,
    Usage,
)
from tests.responses.conftest import (
    ValidationError,
    validate_as,
    validate_event,
)

# The 32 event types the builders produce
IN_SCOPE = {
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

_ID = "msg_1"
_IDX = {"item_id": _ID, "output_index": 0}

_TEXT = "Hi"
_logprob = Logprob(
    token=_TEXT,
    bytes=[72, 105],
    logprob=-0.1,
    top_logprobs=[
        LogprobTopLogprob(token=_TEXT, bytes=[72, 105], logprob=-0.1)
    ],
)
_citation = UrlCitation(
    url="https://a.b", title="T", start_index=0, end_index=2
)


def _items() -> list[ResponseOutputItem]:
    """One of each item type the SDK builds, populated beyond the defaults."""
    return [
        ResponseOutputMessage(
            id="msg_1",
            status=ItemStatus.COMPLETED,
            phase=MessagePhase.FINAL_ANSWER,
            content=[
                ResponseOutputText(
                    text="Hi", annotations=[_citation], logprobs=[_logprob]
                ),
                ResponseOutputRefusal(refusal="No"),
            ],
        ),
        ResponseReasoningItem(
            id="rs_1",
            status=ItemStatus.INCOMPLETE,
            summary=[ReasoningSummary(text="Sum")],
            content=[ReasoningContent(text="Think")],
            encrypted_content="enc",
        ),
        ResponseFunctionToolCall(
            id="fc_1", call_id="call_1", name="f", arguments='{"a":1}'
        ),
        ResponseCustomToolCall(
            id="ctc_1", call_id="call_2", name="g", input="x"
        ),
        ResponseFunctionWebSearch(
            id="ws_1",
            status="failed",
            action=SearchAction(
                query="q", sources=[SearchSource(url="https://a.b")]
            ),
        ),
        ImageGenerationCall(id="ig_1", status="completed", result="b64"),
    ]


def _response_object(**fields: Any) -> ResponseObject:
    return ResponseObject(
        id="resp_1", created_at=1700000000, model="m", **fields
    )


def _usage() -> Usage:
    return Usage(
        input_tokens=3,
        output_tokens=2,
        total_tokens=5,
        input_tokens_details=InputTokensDetails(
            cached_tokens=1, cache_write_tokens=0
        ),
        output_tokens_details=OutputTokensDetails(reasoning_tokens=1),
    )


# (case id, the event type it must produce, the constructor call)
_Case = tuple[str, str, Callable[[], Event]]

_CASES: list[_Case] = [
    # lifecycle
    (
        "response.created",
        "response.created",
        lambda: events.response_created(response=_response_object()),
    ),
    (
        "response.in_progress",
        "response.in_progress",
        lambda: events.response_in_progress(response=_response_object()),
    ),
    (
        "response.completed",
        "response.completed",
        lambda: events.response_completed(
            response=_response_object(
                status=ResponseStatus.COMPLETED,
                output=_items(),
                usage=_usage(),
                tools=[{"type": "function", "name": "f", "parameters": {}}],
                tool_choice={"type": "function", "name": "f"},
                parallel_tool_calls=False,
            )
        ),
    ),
    (
        "response.incomplete",
        "response.incomplete",
        lambda: events.response_incomplete(
            response=_response_object(
                status=ResponseStatus.INCOMPLETE,
                incomplete_details=IncompleteDetails(
                    reason=IncompleteReason.MAX_OUTPUT_TOKENS
                ),
            )
        ),
    ),
    (
        "response.failed",
        "response.failed",
        lambda: events.response_failed(
            response=_response_object(
                status=ResponseStatus.FAILED,
                output=_items(),
                error=ResponseError(
                    code=ErrorCode.SERVER_ERROR, message="Boom"
                ),
            )
        ),
    ),
    # error
    (
        "error",
        "error",
        lambda: events.error(code=ErrorCode.INVALID_PROMPT, message="Bad"),
    ),
    (
        "error-param",
        "error",
        lambda: events.error(
            code=ErrorCode.INVALID_PROMPT, message="Bad", param="input"
        ),
    ),
    # item, once per item type
    *[
        (
            f"{event_type}-{item.type}",
            event_type,
            (lambda c=constructor, i=item: c(output_index=0, item=i)),
        )
        for event_type, constructor in [
            ("response.output_item.added", events.output_item_added),
            ("response.output_item.done", events.output_item_done),
        ]
        for item in _items()
    ],
    # part, once per part type
    *[
        (
            f"{event_type}-{part.type}",
            event_type,
            (lambda c=constructor, p=part: c(**_IDX, content_index=0, part=p)),
        )
        for event_type, constructor in [
            ("response.content_part.added", events.content_part_added),
            ("response.content_part.done", events.content_part_done),
        ]
        for part in [
            ResponseOutputText(),
            ResponseOutputRefusal(),
            ReasoningContent(),
        ]
    ],
    # text
    (
        "response.output_text.delta",
        "response.output_text.delta",
        lambda: events.output_text_delta(
            **_IDX, content_index=0, delta="Hi", logprobs=[]
        ),
    ),
    (
        "response.output_text.delta-logprobs",
        "response.output_text.delta",
        lambda: events.output_text_delta(
            **_IDX, content_index=0, delta="Hi", logprobs=[_logprob]
        ),
    ),
    (
        "response.output_text.done",
        "response.output_text.done",
        lambda: events.output_text_done(
            **_IDX, content_index=0, text="Hi", logprobs=[_logprob]
        ),
    ),
    (
        "response.output_text.annotation.added",
        "response.output_text.annotation.added",
        lambda: events.output_text_annotation_added(
            **_IDX, content_index=0, annotation_index=0, annotation=_citation
        ),
    ),
    # refusal
    (
        "response.refusal.delta",
        "response.refusal.delta",
        lambda: events.refusal_delta(**_IDX, content_index=0, delta="No"),
    ),
    (
        "response.refusal.done",
        "response.refusal.done",
        lambda: events.refusal_done(**_IDX, content_index=0, refusal="No"),
    ),
    # summary
    (
        "response.reasoning_summary_part.added",
        "response.reasoning_summary_part.added",
        lambda: events.reasoning_summary_part_added(
            **_IDX, summary_index=0, part=ReasoningSummary()
        ),
    ),
    (
        "response.reasoning_summary_text.delta",
        "response.reasoning_summary_text.delta",
        lambda: events.reasoning_summary_text_delta(
            **_IDX, summary_index=0, delta="Sum"
        ),
    ),
    (
        "response.reasoning_summary_text.done",
        "response.reasoning_summary_text.done",
        lambda: events.reasoning_summary_text_done(
            **_IDX, summary_index=0, text="Sum"
        ),
    ),
    (
        "response.reasoning_summary_part.done",
        "response.reasoning_summary_part.done",
        lambda: events.reasoning_summary_part_done(
            **_IDX, summary_index=0, part=ReasoningSummary(text="Sum")
        ),
    ),
    (
        "response.reasoning_summary_part.done-incomplete",
        "response.reasoning_summary_part.done",
        lambda: events.reasoning_summary_part_done(
            **_IDX,
            summary_index=0,
            part=ReasoningSummary(text="Su"),
            incomplete=True,
        ),
    ),
    # reasoning
    (
        "response.reasoning_text.delta",
        "response.reasoning_text.delta",
        lambda: events.reasoning_text_delta(
            **_IDX, content_index=0, delta="Think"
        ),
    ),
    (
        "response.reasoning_text.done",
        "response.reasoning_text.done",
        lambda: events.reasoning_text_done(
            **_IDX, content_index=0, text="Think"
        ),
    ),
    # function
    (
        "response.function_call_arguments.delta",
        "response.function_call_arguments.delta",
        lambda: events.function_call_arguments_delta(**_IDX, delta='{"a"'),
    ),
    (
        "response.function_call_arguments.done",
        "response.function_call_arguments.done",
        lambda: events.function_call_arguments_done(
            **_IDX, name="f", arguments='{"a":1}'
        ),
    ),
    # custom tool
    (
        "response.custom_tool_call_input.delta",
        "response.custom_tool_call_input.delta",
        lambda: events.custom_tool_call_input_delta(**_IDX, delta="x"),
    ),
    (
        "response.custom_tool_call_input.done",
        "response.custom_tool_call_input.done",
        lambda: events.custom_tool_call_input_done(**_IDX, input="x"),
    ),
    # web search
    (
        "response.web_search_call.in_progress",
        "response.web_search_call.in_progress",
        lambda: events.web_search_call_in_progress(**_IDX),
    ),
    (
        "response.web_search_call.searching",
        "response.web_search_call.searching",
        lambda: events.web_search_call_searching(**_IDX),
    ),
    (
        "response.web_search_call.completed",
        "response.web_search_call.completed",
        lambda: events.web_search_call_completed(**_IDX),
    ),
    # image generation
    (
        "response.image_generation_call.in_progress",
        "response.image_generation_call.in_progress",
        lambda: events.image_generation_call_in_progress(**_IDX),
    ),
    (
        "response.image_generation_call.generating",
        "response.image_generation_call.generating",
        lambda: events.image_generation_call_generating(**_IDX),
    ),
    (
        "response.image_generation_call.partial_image",
        "response.image_generation_call.partial_image",
        lambda: events.image_generation_call_partial_image(
            **_IDX, partial_image_index=0, partial_image_b64="b64"
        ),
    ),
    (
        "response.image_generation_call.completed",
        "response.image_generation_call.completed",
        lambda: events.image_generation_call_completed(**_IDX),
    ),
]


def _enums(data: Any) -> list[Enum]:
    if isinstance(data, Enum):
        return [data]
    if isinstance(data, dict):
        return [e for value in data.values() for e in _enums(value)]
    if isinstance(data, list):
        return [e for value in data for e in _enums(value)]
    return []


def _numbered(event: Event) -> Event:
    """What the response context does on emit."""
    event["sequence_number"] = 0
    return event


@pytest.mark.parametrize(
    "event_type, construct",
    [(t, c) for _, t, c in _CASES],
    ids=[i for i, _, _ in _CASES],
)
def test_event_is_valid(event_type: str, construct: Callable[[], Event]):
    event = construct()

    assert list(event)[:2] == ["type", "sequence_number"]
    assert event["type"] == event_type
    assert event["sequence_number"] is None
    assert not _enums(event)

    validate_event(_numbered(event))


def test_annotation_is_valid():
    # The event types the annotation as `object`, so it is checked on its own
    event = events.output_text_annotation_added(
        **_IDX, content_index=0, annotation_index=0, annotation=_citation
    )
    validate_as(openai_text.Annotation, event["annotation"])


def test_every_event_type_in_scope_is_covered():
    assert {t for _, t, _ in _CASES} == IN_SCOPE


def test_scope_matches_openai():
    openai_types = {
        get_args(member.__annotations__["type"])[0]
        for member in get_args(get_args(ResponseStreamEvent)[0])
    }
    assert len(openai_types) == 53
    assert openai_types >= IN_SCOPE
    assert len(openai_types - IN_SCOPE) == 21


def test_text_logprobs_have_no_bytes():
    event = events.output_text_delta(
        **_IDX, content_index=0, delta="Hi", logprobs=[_logprob]
    )
    assert event["logprobs"] == [
        {
            "token": "Hi",
            "logprob": -0.1,
            "top_logprobs": [{"token": "Hi", "logprob": -0.1}],
        }
    ]


# Events carry payloads serialised at construction, never a reference to
# the live response object


def test_summary_part_status_is_omitted_unless_incomplete():
    part = ReasoningSummary(text="Sum")

    done = events.reasoning_summary_part_done(
        **_IDX, summary_index=0, part=part
    )
    incomplete = events.reasoning_summary_part_done(
        **_IDX, summary_index=0, part=part, incomplete=True
    )

    assert "status" not in done
    assert incomplete["status"] == "incomplete"


def test_lifecycle_event_does_not_track_the_response_object():
    response_object = _response_object(
        tools=[{"type": "function", "name": "f"}]
    )
    created = events.response_created(response=response_object)
    expected = copy.deepcopy(created)

    response_object.status = ResponseStatus.COMPLETED
    response_object.output.extend(_items())
    response_object.usage = _usage()
    response_object.tools[0]["name"] = "g"
    response_object.tools.append({"type": "custom", "name": "h"})

    assert created == expected
    assert created["response"]["output"] == []
    assert created["response"]["status"] == "in_progress"


def test_item_event_does_not_track_the_item():
    message = ResponseOutputMessage(id=_ID)
    added = events.output_item_added(output_index=0, item=message)
    expected = copy.deepcopy(added)

    text = ResponseOutputText()
    message.content.append(text)
    text.text = "Hi"
    message.status = ItemStatus.COMPLETED

    assert added == expected
    assert added["item"]["content"] == []
    assert added["item"]["status"] == "in_progress"


def test_part_event_does_not_track_the_part():
    part = ResponseOutputText()
    added = events.content_part_added(**_IDX, content_index=0, part=part)
    expected = copy.deepcopy(added)

    part.text = "Hi"
    part.annotations.append(_citation)

    assert added == expected
    assert added["part"] == {
        "type": "output_text",
        "text": "",
        "annotations": [],
        "logprobs": None,
    }


# The validator must be able to fail, or it proves nothing


def test_validator_rejects_an_unnumbered_event():
    event = events.web_search_call_completed(**_IDX)
    with pytest.raises(ValidationError):
        validate_event(event)


def test_validator_rejects_an_extra_field():
    event = _numbered(
        events.refusal_done(**_IDX, content_index=0, refusal="No")
    )
    event["text"] = "No"
    with pytest.raises(AssertionError, match="Fields unknown to openai"):
        validate_event(event)


def test_validator_rejects_a_nested_extra_field():
    item = ResponseCustomToolCall(id="ctc_1", call_id="call_1", name="g")
    event = _numbered(events.output_item_added(output_index=0, item=item))
    event["item"]["status"] = "completed"
    with pytest.raises(AssertionError, match="Fields unknown to openai"):
        validate_event(event)
