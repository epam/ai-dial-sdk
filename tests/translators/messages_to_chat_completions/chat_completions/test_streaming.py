import json

import pytest
from openai.types.chat import ChatCompletionChunk
from openai.types.chat.chat_completion_chunk import (
    ChoiceDelta,
    ChoiceDeltaToolCall,
    ChoiceDeltaToolCallFunction,
)
from openai.types.completion_usage import (
    CompletionTokensDetails,
    CompletionUsage,
    PromptTokensDetails,
)

from aidial_sdk.translators.messages_to_chat_completions.chat_completions.streaming import (
    translate_stream,
)
from aidial_sdk.translators.messages_to_chat_completions.translation_state import (
    TranslationState,
)
from tests.translators.messages_to_chat_completions.helpers import (
    FakeStream,
    chunk,
    parse_anthropic_sse,
)

LONG_MCP_NAME = "mcp__" + "s" * 60 + "__do_the_thing"


async def translate(
    chunks: list[ChatCompletionChunk],
    model: str = "gpt-5.5",
    translation_state: TranslationState | None = None,
):
    stream = FakeStream(chunks)
    collected = b""
    async for event_bytes in translate_stream(
        stream,
        model,
        translation_state or TranslationState(),
    ):
        collected += event_bytes
    assert stream.closed
    return parse_anthropic_sse(collected)


def usage_chunk(
    prompt: int = 5, completion: int = 2, cached: int = 0
) -> ChatCompletionChunk:
    return chunk(
        choices=[],
        usage=CompletionUsage(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
            prompt_tokens_details=PromptTokensDetails(cached_tokens=cached),
        ),
    )


def text_of(events) -> str:
    return "".join(
        data["delta"]["text"]
        for name, data in events
        if name == "content_block_delta"
        and data["delta"]["type"] == "text_delta"
    )


def assert_block_discipline(events) -> None:
    open_blocks: dict[int, str] = {}
    seen_indices: list[int] = []
    for position, (name, data) in enumerate(events):
        if name == "content_block_start":
            assert data["index"] not in open_blocks
            block_type = data["content_block"]["type"]
            assert not open_blocks or (
                block_type == "tool_use"
                and all(kind == "tool_use" for kind in open_blocks.values())
            ), "only parallel tool blocks may overlap"
            open_blocks[data["index"]] = block_type
            seen_indices.append(data["index"])
        elif name == "content_block_delta":
            assert data["index"] in open_blocks, "delta against a closed block"
        elif name == "content_block_stop":
            assert data["index"] in open_blocks, "stop for a non-open block"
            del open_blocks[data["index"]]
        elif name == "message_stop":
            assert position == len(events) - 1, "events follow message_stop"
    assert not open_blocks, "a block was left open"

    assert seen_indices == list(range(len(seen_indices)))


async def test_plain_text_stream() -> None:
    events = await translate(
        [
            chunk(ChoiceDelta(role="assistant", content="Hello")),
            chunk(ChoiceDelta(content=" world"), finish_reason="stop"),
            usage_chunk(),
        ]
    )
    assert [name for name, _ in events] == [
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]
    assert_block_discipline(events)
    assert events[0][1]["message"]["id"] == "chatcmpl_1"
    assert events[0][1]["message"]["stop_reason"] is None

    assert events[1][1]["content_block"] == {"type": "text", "text": ""}
    assert text_of(events) == "Hello world"

    message_delta = events[5][1]

    assert message_delta["delta"] == {
        "stop_reason": "end_turn",
        "stop_sequence": None,
    }

    assert (
        message_delta["usage"].items()
        >= {
            "input_tokens": 5,
            "output_tokens": 2,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        }.items()
    )


async def test_tool_call_stream() -> None:
    events = await translate(
        [
            chunk(
                ChoiceDelta(
                    tool_calls=[
                        ChoiceDeltaToolCall(
                            index=0,
                            id="call_1",
                            type="function",
                            function=ChoiceDeltaToolCallFunction(
                                name="get_weather", arguments=""
                            ),
                        )
                    ]
                )
            ),
            chunk(
                ChoiceDelta(
                    tool_calls=[
                        ChoiceDeltaToolCall(
                            index=0,
                            function=ChoiceDeltaToolCallFunction(
                                arguments='{"city"'
                            ),
                        )
                    ]
                )
            ),
            chunk(
                ChoiceDelta(
                    tool_calls=[
                        ChoiceDeltaToolCall(
                            index=0,
                            function=ChoiceDeltaToolCallFunction(
                                arguments=': "NYC"}'
                            ),
                        )
                    ]
                ),
                finish_reason="tool_calls",
            ),
            usage_chunk(),
        ]
    )
    assert_block_discipline(events)

    assert events[1][1]["content_block"] == {
        "type": "tool_use",
        "id": "call_1",
        "name": "get_weather",
        "input": {},
    }
    partials = [
        data["delta"]["partial_json"]
        for name, data in events
        if name == "content_block_delta"
    ]
    assert partials == ['{"city"', ': "NYC"}']
    assert events[-2][1]["delta"]["stop_reason"] == "tool_use"


async def test_an_aliased_tool_name_is_restored() -> None:
    translation_state = TranslationState()
    alias = translation_state.to_upstream_tool_name(LONG_MCP_NAME)
    events = await translate(
        [
            chunk(
                ChoiceDelta(
                    tool_calls=[
                        ChoiceDeltaToolCall(
                            index=0,
                            id="call_1",
                            type="function",
                            function=ChoiceDeltaToolCallFunction(name=alias),
                        )
                    ]
                ),
                finish_reason="tool_calls",
            ),
            usage_chunk(),
        ],
        translation_state=translation_state,
    )
    start = next(d for name, d in events if name == "content_block_start")
    assert start["content_block"]["name"] == LONG_MCP_NAME


async def test_opening_a_tool_block_closes_the_open_text_block() -> None:
    events = await translate(
        [
            chunk(ChoiceDelta(content="thinking about it")),
            chunk(
                ChoiceDelta(
                    tool_calls=[
                        ChoiceDeltaToolCall(
                            index=0,
                            id="call_1",
                            type="function",
                            function=ChoiceDeltaToolCallFunction(name="search"),
                        )
                    ]
                ),
                finish_reason="tool_calls",
            ),
            usage_chunk(),
        ]
    )
    assert_block_discipline(events)
    assert [name for name, _ in events].count("content_block_start") == 2


async def test_reasoning_stages_become_a_thinking_block() -> None:
    events = await translate(
        [
            chunk(
                {
                    "custom_content": {
                        "stages": [
                            {"index": 0, "name": "Thinking", "content": "let "}
                        ]
                    }
                }
            ),
            chunk(
                {"custom_content": {"stages": [{"index": 0, "content": "me"}]}}
            ),
            chunk(ChoiceDelta(content="answer"), finish_reason="stop"),
            usage_chunk(),
        ]
    )
    assert_block_discipline(events)
    start = events[1]
    assert start[0] == "content_block_start"
    assert start[1]["content_block"]["type"] == "thinking"
    thinking = "".join(
        data["delta"]["thinking"]
        for name, data in events
        if name == "content_block_delta"
        and data["delta"]["type"] == "thinking_delta"
    )
    assert thinking == "let me"
    assert text_of(events) == "answer"


async def test_a_non_reasoning_stage_is_ignored() -> None:
    events = await translate(
        [
            chunk(
                {
                    "custom_content": {
                        "stages": [
                            {"index": 0, "name": "Searching", "content": "x"}
                        ]
                    }
                }
            ),
            chunk(ChoiceDelta(content="answer"), finish_reason="stop"),
            usage_chunk(),
        ]
    )
    assert [
        data["content_block"]["type"]
        for name, data in events
        if name == "content_block_start"
    ] == ["text"]
    assert text_of(events) == "answer"


@pytest.mark.parametrize(
    "thinking", [{"thinking": "hmm"}, {}], ids=["with-text", "signature-only"]
)
async def test_a_signature_closes_the_thinking_block(
    thinking: dict[str, str],
) -> None:
    events = await translate(
        [
            chunk(
                {
                    "custom_content": {
                        "stages": [
                            {"index": 0, "name": "Thinking", "content": "hmm"}
                        ]
                    }
                }
            ),
            chunk(
                {
                    "custom_content": {
                        "state": {
                            "claude_message_content": [
                                {
                                    "type": "thinking",
                                    **thinking,
                                    "signature": "sig-abc",
                                }
                            ]
                        }
                    }
                }
            ),
            chunk(ChoiceDelta(content="answer"), finish_reason="stop"),
            usage_chunk(),
        ]
    )
    assert_block_discipline(events)
    names = [name for name, _ in events]
    signature_at = next(
        i
        for i, (name, data) in enumerate(events)
        if name == "content_block_delta"
        and data["delta"]["type"] == "signature_delta"
    )
    assert events[signature_at][1]["delta"]["signature"] == "sig-abc"

    assert names[signature_at + 1] == "content_block_stop"


async def test_a_signature_after_the_block_closed_is_dropped_not_fatal() -> (
    None
):
    events = await translate(
        [
            chunk(
                {
                    "custom_content": {
                        "stages": [
                            {"index": 0, "name": "Thinking", "content": "hmm"}
                        ]
                    }
                }
            ),
            chunk(ChoiceDelta(content="answer")),
            chunk(
                {
                    "custom_content": {
                        "state": {
                            "claude_message_content": [
                                {
                                    "type": "thinking",
                                    "thinking": "hmm",
                                    "signature": "sig",
                                }
                            ]
                        }
                    }
                },
                finish_reason="stop",
            ),
            usage_chunk(),
        ]
    )
    assert_block_discipline(events)
    assert text_of(events) == "answer"

    assert not any(
        data.get("delta", {}).get("type") == "signature_delta"
        for _, data in events
    )


def annotation(url: str, title: str = "T") -> dict[str, object]:
    return {
        "type": "url_citation",
        "url_citation": {
            "url": url,
            "title": title,
            "start_index": 0,
            "end_index": 1,
        },
    }


async def test_annotations_become_citation_blocks() -> None:
    events = await translate(
        [
            chunk(ChoiceDelta(content="answer")),
            chunk({"annotations": [annotation("https://e.com")]}),
            chunk(ChoiceDelta(), finish_reason="stop"),
            usage_chunk(),
        ]
    )
    assert_block_discipline(events)
    types = [
        data["content_block"]["type"]
        for name, data in events
        if name == "content_block_start"
    ]
    assert types == ["text", "server_tool_use", "web_search_tool_result"]


async def test_a_resent_annotation_array_renders_each_citation_once() -> None:
    events = await translate(
        [
            chunk(
                {
                    "annotations": [
                        annotation("https://a.com"),
                        annotation("https://b.com"),
                    ]
                }
            ),
            chunk(
                {
                    "annotations": [
                        annotation("https://a.com"),
                        annotation("https://c.com"),
                    ]
                },
                finish_reason="stop",
            ),
            usage_chunk(),
        ]
    )
    assert_block_discipline(events)
    urls = [
        [item["url"] for item in data["content_block"]["content"]]
        for name, data in events
        if name == "content_block_start"
        and data["content_block"]["type"] == "web_search_tool_result"
    ]
    assert urls == [["https://a.com", "https://b.com"], ["https://c.com"]]


async def test_usage_on_a_content_chunk_does_not_truncate() -> None:
    events = await translate(
        [
            chunk(ChoiceDelta(role="assistant", content="Hel")),
            chunk(
                ChoiceDelta(content="lo"),
                usage=CompletionUsage(
                    prompt_tokens=5, completion_tokens=1, total_tokens=6
                ),
            ),
            chunk(ChoiceDelta(content=" world"), finish_reason="stop"),
            usage_chunk(prompt=5, completion=2),
        ]
    )
    names = [name for name, _ in events]
    assert names.count("message_stop") == 1
    assert names[-1] == "message_stop"
    assert text_of(events) == "Hello world"
    message_delta = next(d for name, d in events if name == "message_delta")
    assert message_delta["usage"]["output_tokens"] == 2


async def test_usage_split_across_chunks_is_merged() -> None:
    events = await translate(
        [
            chunk(
                ChoiceDelta(content="hi"),
                usage=CompletionUsage(
                    prompt_tokens=100,
                    completion_tokens=0,
                    total_tokens=100,
                    prompt_tokens_details=PromptTokensDetails(cached_tokens=30),
                ),
            ),
            chunk(ChoiceDelta(), finish_reason="stop"),
            chunk(
                choices=[],
                usage=CompletionUsage(
                    prompt_tokens=100, completion_tokens=7, total_tokens=107
                ),
            ),
        ]
    )
    assert_block_discipline(events)
    usage = next(d for name, d in events if name == "message_delta")["usage"]
    assert usage["input_tokens"] == 70
    assert usage["cache_read_input_tokens"] == 30
    assert usage["output_tokens"] == 7


async def test_stream_without_usage_chunk_still_finalizes() -> None:
    events = await translate(
        [
            chunk(ChoiceDelta(role="assistant", content="hi")),
            chunk(ChoiceDelta(), finish_reason="length"),
        ]
    )
    assert [name for name, _ in events][-1] == "message_stop"
    message_delta = next(d for name, d in events if name == "message_delta")
    assert message_delta["delta"]["stop_reason"] == "max_tokens"
    assert message_delta["usage"]["input_tokens"] == 0


async def test_an_upstream_yielding_no_chunks_still_emits_message_start() -> (
    None
):
    events = await translate([])
    assert [name for name, _ in events] == [
        "message_start",
        "content_block_start",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]
    assert_block_discipline(events)
    assert events[1][1]["content_block"] == {"type": "text", "text": ""}


async def test_a_stream_with_no_content_gets_the_zero_block_guard() -> None:
    events = await translate(
        [chunk(ChoiceDelta(), finish_reason="stop"), usage_chunk()]
    )
    assert_block_discipline(events)
    starts = [d for name, d in events if name == "content_block_start"]
    assert len(starts) == 1
    assert starts[0]["content_block"]["text"] == ""


async def test_cached_tokens_are_subtracted_in_streaming_too() -> None:
    events = await translate(
        [
            chunk(ChoiceDelta(content="hi"), finish_reason="stop"),
            usage_chunk(prompt=100, completion=20, cached=30),
        ]
    )
    usage = next(d for name, d in events if name == "message_delta")["usage"]
    assert usage["input_tokens"] == 70
    assert usage["cache_read_input_tokens"] == 30
    assert usage["cache_creation_input_tokens"] == 0


async def test_streaming_usage_accounts_for_cache_and_reasoning_tokens() -> (
    None
):
    usage = CompletionUsage(
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        prompt_tokens_details=PromptTokensDetails.model_validate(
            {"cached_tokens": 30, "cache_write_tokens": 25}
        ),
        completion_tokens_details=CompletionTokensDetails(reasoning_tokens=40),
    )
    events = await translate(
        [
            chunk(ChoiceDelta(content="hi"), finish_reason="stop"),
            chunk(choices=[], usage=usage),
        ]
    )
    streamed = next(d for name, d in events if name == "message_delta")["usage"]

    assert streamed == {
        "input_tokens": 45,
        "output_tokens": 50,
        "cache_read_input_tokens": 30,
        "cache_creation_input_tokens": 25,
        "output_tokens_details": {"thinking_tokens": 40},
    }


async def test_refusal_stream() -> None:
    events = await translate(
        [
            chunk(ChoiceDelta(role="assistant", refusal="I can't")),
            chunk(ChoiceDelta(), finish_reason="stop"),
            usage_chunk(),
        ]
    )
    assert text_of(events) == "I can't"
    assert events[-2][1]["delta"]["stop_reason"] == "refusal"


async def test_parallel_tool_fragments_keep_their_original_indices() -> None:
    stream_events = await translate(
        [
            chunk(
                {
                    "tool_calls": [
                        {
                            "index": i,
                            "id": f"call_{i}",
                            "function": {"name": f"tool_{i}", "arguments": "{"},
                        }
                        for i in range(2)
                    ]
                }
            ),
            chunk(
                {
                    "tool_calls": [
                        {"index": 0, "function": {"arguments": '"a":1}'}},
                        {"index": 1, "function": {"arguments": '"b":2}'}},
                    ]
                },
                finish_reason="tool_calls",
            ),
        ]
    )
    assert_block_discipline(stream_events)
    result = [data for _, data in stream_events]
    starts = [e for e in result if e["type"] == "content_block_start"]
    assert len(starts) == 2
    for i, expected in enumerate([{"a": 1}, {"b": 2}]):
        args = "".join(
            e["delta"]["partial_json"]
            for e in result
            if e["type"] == "content_block_delta" and e["index"] == i
        )
        assert json.loads(args) == expected
        assert starts[i]["content_block"]["id"] == f"call_{i}"
        assert (
            sum(
                e["type"] == "content_block_stop" and e["index"] == i
                for e in result
            )
            == 1
        )
