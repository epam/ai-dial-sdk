from typing import Any
from unittest.mock import ANY

import pytest

from aidial_sdk.translators._messages.sse_stream import (
    HEARTBEAT,
    Heartbeat,
)
from aidial_sdk.translators._messages.translation_state import (
    TranslationState,
)
from aidial_sdk.translators.messages_to_responses.streaming import (
    translate_stream,
)
from tests.translators.messages_to_chat_completions.helpers import (
    FakeStream,
    parse_anthropic_sse,
)
from tests.translators.messages_to_responses.helpers import (
    function_call_item,
    reasoning_item,
    responses_body,
    signature,
    text_item,
    url_citation,
)

Event = dict[str, Any]


async def translate(
    events: list[Event | Heartbeat], raise_after: Exception | None = None
) -> list[tuple[str, Any]]:
    stream = FakeStream(events, raise_after)
    collected = b""
    async for chunk in translate_stream(
        stream.generator, "gpt-5.5", TranslationState()
    ):
        collected += chunk
    assert stream.closed
    return parse_anthropic_sse(collected)


def created() -> Event:
    return {
        "type": "response.created",
        "response": responses_body([], status="in_progress"),
    }


def completed(output: list[dict[str, object]], **fields: Any) -> Event:
    return {
        "type": "response.completed",
        "response": responses_body(output, **fields),
    }


def item_added(index: int, item: dict[str, object]) -> Event:
    return {
        "type": "response.output_item.added",
        "output_index": index,
        "item": item,
    }


def item_done(index: int, item: dict[str, object]) -> Event:
    return {
        "type": "response.output_item.done",
        "output_index": index,
        "item": item,
    }


def text_delta(index: int, delta: str, content_index: int = 0) -> Event:
    return {
        "type": "response.output_text.delta",
        "output_index": index,
        "content_index": content_index,
        "delta": delta,
    }


def summary_delta(index: int, delta: str, summary_index: int = 0) -> Event:
    return {
        "type": "response.reasoning_summary_text.delta",
        "output_index": index,
        "summary_index": summary_index,
        "delta": delta,
    }


def arguments_delta(index: int, delta: str) -> Event:
    return {
        "type": "response.function_call_arguments.delta",
        "output_index": index,
        "delta": delta,
    }


def block_events(events: list[tuple[str, Any]]) -> list[Any]:
    """The content block events, without the message ones."""
    return [data for name, data in events if name.startswith("content_block")]


async def test_text() -> None:
    events = await translate(
        [
            created(),
            text_delta(0, "Hel"),
            text_delta(0, "lo"),
            item_done(0, text_item("Hello")),
            completed(
                [text_item("Hello")],
                usage={
                    "input_tokens": 10,
                    "input_tokens_details": {"cached_tokens": 4},
                    "output_tokens": 5,
                    "output_tokens_details": {"reasoning_tokens": 0},
                    "total_tokens": 15,
                },
            ),
        ]
    )
    assert events == [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "resp_1",
                    "type": "message",
                    "role": "assistant",
                    "model": "gpt-5.5",
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0,
                    },
                },
            },
        ),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "Hel"},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "lo"},
            },
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {
                    "input_tokens": 6,
                    "output_tokens": 5,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 4,
                    "output_tokens_details": {"thinking_tokens": 0},
                },
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]


async def test_reasoning_is_signed_when_its_item_is_done() -> None:
    item = reasoning_item(["One", "Two"])
    events = await translate(
        [
            created(),
            summary_delta(0, "One"),
            summary_delta(0, "Two", summary_index=1),
            item_done(0, item),
            completed([item]),
        ]
    )
    assert block_events(events) == [
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {
                "type": "thinking",
                "thinking": "",
                "signature": "",
            },
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "thinking_delta", "thinking": "One"},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "thinking_delta", "thinking": "\n\nTwo"},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "signature_delta", "signature": signature()},
        },
        {"type": "content_block_stop", "index": 0},
    ]


async def test_reasoning_without_streamed_text_is_one_redacted_block() -> None:
    item = reasoning_item([])
    events = await translate([created(), item_done(0, item), completed([item])])
    assert block_events(events) == [
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "redacted_thinking", "data": signature()},
        },
        {"type": "content_block_stop", "index": 0},
    ]


async def test_function_call() -> None:
    item = function_call_item()
    events = await translate(
        [
            created(),
            item_added(0, {**item, "arguments": ""}),
            arguments_delta(0, '{"q": '),
            arguments_delta(0, '"x"}'),
            item_done(0, item),
            completed([item]),
        ]
    )
    assert block_events(events) == [
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {
                "type": "tool_use",
                "id": "call_1",
                "name": "search",
                "input": {},
            },
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": '{"q": '},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": '"x"}'},
        },
        {"type": "content_block_stop", "index": 0},
    ]
    assert events[-2][1]["delta"]["stop_reason"] == "tool_use"


async def test_arguments_sent_without_deltas_are_sent_whole() -> None:
    item = function_call_item()
    events = await translate(
        [
            created(),
            item_added(0, {**item, "arguments": ""}),
            item_done(0, item),
            completed([item]),
        ]
    )
    assert [
        data["delta"] for data in block_events(events) if "delta" in data
    ] == [{"type": "input_json_delta", "partial_json": '{"q": "x"}'}]


async def test_citations_follow_the_message() -> None:
    item = text_item("Hi", [url_citation("https://a")])
    events = await translate(
        [created(), text_delta(0, "Hi"), item_done(0, item), completed([item])]
    )
    assert [
        data["content_block"]
        for data in block_events(events)
        if data["type"] == "content_block_start"
    ] == [
        {"type": "text", "text": ""},
        {
            "type": "server_tool_use",
            "id": ANY,
            "name": "web_search",
            "input": {"query": ""},
        },
        {
            "type": "web_search_tool_result",
            "tool_use_id": ANY,
            "content": [
                {
                    "type": "web_search_result",
                    "url": "https://a",
                    "title": "Title",
                    "encrypted_content": "",
                }
            ],
        },
    ]


async def test_heartbeat_is_a_ping() -> None:
    events = await translate([created(), HEARTBEAT, completed([])])
    assert [name for name, _ in events] == [
        "message_start",
        "ping",
        "content_block_start",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]


async def test_unknown_event_is_ignored() -> None:
    events = await translate(
        [created(), {"type": "response.teleport.delta"}, completed([])]
    )
    assert [name for name, _ in events][-2:] == [
        "message_delta",
        "message_stop",
    ]


async def test_incomplete_response_stops_on_max_tokens() -> None:
    events = await translate(
        [
            created(),
            text_delta(0, "Hi"),
            {
                "type": "response.incomplete",
                "response": responses_body(
                    [],
                    status="incomplete",
                    incomplete_details={"reason": "max_output_tokens"},
                ),
            },
        ]
    )
    assert events[-2][1]["delta"]["stop_reason"] == "max_tokens"


async def test_failed_response_is_an_error_event() -> None:
    events = await translate(
        [
            created(),
            {
                "type": "response.failed",
                "response": responses_body(
                    [],
                    status="failed",
                    error={
                        "code": "rate_limit_exceeded",
                        "message": "Slow down",
                    },
                ),
            },
        ]
    )
    assert events[-1] == (
        "error",
        {
            "type": "error",
            "error": {"type": "rate_limit_error", "message": "Slow down"},
        },
    )


@pytest.mark.parametrize(
    "code, error_type",
    [
        ("server_error", "api_error"),
        ("invalid_prompt", "invalid_request_error"),
        ("rate_limit_exceeded", "rate_limit_error"),
        (None, "api_error"),
    ],
    ids=["server-error", "invalid-prompt", "rate-limit", "no-code"],
)
async def test_error_event_is_an_error_event(
    code: str | None, error_type: str
) -> None:
    events = await translate(
        [
            created(),
            {
                "type": "error",
                "code": code,
                "message": "Oops",
                "sequence_number": 1,
            },
        ]
    )
    assert events[-1] == (
        "error",
        {"type": "error", "error": {"type": error_type, "message": "Oops"}},
    )


async def test_stream_ending_without_a_final_event_is_an_error() -> None:
    events = await translate([created(), text_delta(0, "Hi")])
    assert events[-1] == (
        "error",
        {
            "type": "error",
            "error": {
                "type": "api_error",
                "message": "The Responses API stream ended before the response completed",
            },
        },
    )


async def test_exception_in_the_stream_is_an_error_event() -> None:
    events = await translate([created()], raise_after=RuntimeError("boom"))
    assert events[-1] == (
        "error",
        {
            "type": "error",
            "error": {"type": "api_error", "message": "Internal server error"},
        },
    )
