import pytest
from anthropic.types import (
    RawMessageStreamEvent,
    TextBlock,
    ThinkingBlock,
    ToolParam,
    ToolUseBlock,
    Usage,
)
from anthropic.types.output_tokens_details import OutputTokensDetails

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion import FinishReason, Request, Response
from tests.translators.messages_to_chat_completions.auto_translation.helpers import (
    AnthropicClient,
    AppClient,
    Chat,
    ScriptedChatCompletion,
)

_WEATHER_TOOL: ToolParam = {
    "name": "get_weather",
    "input_schema": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
    },
}


def _anthropic_client(chat: Chat) -> AnthropicClient:
    app = DIALApp().add_chat_completion(
        "foo", ScriptedChatCompletion(chat), expose_as_anthropic_messages=True
    )
    return AppClient(app).anthropic()


async def test_content_is_concatenated_into_one_text_block(
    stream: bool,
):
    async def _chat(request: Request, response: Response):
        with response.create_single_choice() as choice:
            choice.append_content("Hel")
            choice.append_content("lo")

    async with _anthropic_client(_chat) as client:
        message = await client.final_message(stream=stream)

    assert message.content == [TextBlock(type="text", text="Hello")]
    assert message.stop_reason == "end_turn"


async def test_content_with_the_sse_done_marker_is_delivered_in_full(
    stream: bool,
):
    async def _chat(request: Request, response: Response):
        with response.create_single_choice() as choice:
            choice.append_content("before [DONE] after")

    async with _anthropic_client(_chat) as client:
        message = await client.final_message(stream=stream)

    assert message.content == [
        TextBlock(type="text", text="before [DONE] after")
    ]


async def test_response_headers_are_passed_through(stream: bool):
    async def _chat(request: Request, response: Response):
        response.append_header("header1", "value1")
        response.append_header("header2", "value2-1")
        response.append_header("header2", "value2-2")
        with response.create_single_choice() as choice:
            choice.append_content("Hello")

    async with _anthropic_client(_chat) as client:
        headers = await client.response_headers(stream=stream)

    assert headers.get("header1") == "value1"
    assert headers.get("header2") == "value2-1, value2-2"


async def test_empty_choice_is_an_empty_text_block(stream: bool):
    async def _chat(request: Request, response: Response):
        with response.create_single_choice():
            pass

    async with _anthropic_client(_chat) as client:
        message = await client.final_message(stream=stream)

    assert message.content == [TextBlock(type="text", text="")]
    assert message.stop_reason == "end_turn"


async def test_response_id_and_deployment_become_message_id_and_model(
    stream: bool,
):
    async def _chat(request: Request, response: Response):
        response.set_response_id("chatcmpl-42")
        with response.create_single_choice() as choice:
            choice.append_content("Hello")

    async with _anthropic_client(_chat) as client:
        message = await client.final_message(stream=stream)

    assert message.id == "chatcmpl-42"
    assert message.model == "foo"


async def test_tool_call_is_a_tool_use_block(stream: bool):
    async def _chat(request: Request, response: Response):
        with response.create_single_choice() as choice:
            choice.create_function_tool_call(
                id="call_1", name="get_weather", arguments='{"city": "Paris"}'
            )

    async with _anthropic_client(_chat) as client:
        message = await client.final_message(
            stream=stream, tools=[_WEATHER_TOOL]
        )

    assert message.content == [
        ToolUseBlock(
            type="tool_use",
            id="call_1",
            name="get_weather",
            input={"city": "Paris"},
        )
    ]
    assert message.stop_reason == "tool_use"


async def test_text_and_parallel_tool_calls_keep_their_order(
    stream: bool,
):
    async def _chat(request: Request, response: Response):
        with response.create_single_choice() as choice:
            choice.append_content("Let me check")
            choice.create_function_tool_call(
                id="call_1", name="get_weather", arguments='{"city": "Paris"}'
            )
            choice.create_function_tool_call(
                id="call_2", name="get_weather", arguments='{"city": "London"}'
            )

    async with _anthropic_client(_chat) as client:
        message = await client.final_message(
            stream=stream, tools=[_WEATHER_TOOL]
        )

    assert message.content == [
        TextBlock(type="text", text="Let me check"),
        ToolUseBlock(
            type="tool_use",
            id="call_1",
            name="get_weather",
            input={"city": "Paris"},
        ),
        ToolUseBlock(
            type="tool_use",
            id="call_2",
            name="get_weather",
            input={"city": "London"},
        ),
    ]
    assert message.stop_reason == "tool_use"


@pytest.mark.parametrize(
    "stage_name",
    [
        "thinking",
        "Thinking",
        "thought",
        "Thought",
        "reasoning",
        "Reasoning",
    ],
)
async def test_thinking_from_dial_stage(stream: bool, stage_name: str):
    async def _chat(request: Request, response: Response):
        with response.create_single_choice() as choice:
            with choice.create_stage(stage_name) as stage:
                stage.append_content("Let me think")
            choice.append_content("Hello")

    async with _anthropic_client(_chat) as client:
        message = await client.final_message(stream=stream)

    assert message.content == [
        ThinkingBlock(type="thinking", thinking="Let me think", signature=""),
        TextBlock(type="text", text="Hello"),
    ]


async def test_thinking_from_state(stream: bool):
    async def _chat(request: Request, response: Response):
        with response.create_single_choice() as choice:
            choice.set_state(
                {
                    "claude_message_content": [
                        {
                            "type": "thinking",
                            "thinking": "Let me think",
                            "signature": "sig",
                        }
                    ]
                }
            )
            choice.append_content("Hello")

    async with _anthropic_client(_chat) as client:
        message = await client.final_message(stream=stream)

    if stream:
        # FIXME: streaming drops the thinking from claude_message_content (issue #487)
        assert message.content == [TextBlock(type="text", text="Hello")]
    else:
        assert message.content == [
            ThinkingBlock(
                type="thinking", thinking="Let me think", signature="sig"
            ),
            TextBlock(type="text", text="Hello"),
        ]


async def test_thinking_from_reasoning_content(stream: bool):
    async def _chat(request: Request, response: Response):
        with response.create_single_choice() as choice:
            choice.append_reasoning_content("Let me think")
            choice.append_content("Hello")

    async with _anthropic_client(_chat) as client:
        message = await client.final_message(stream=stream)

    if stream:
        # FIXME: streaming drops the thinking from reasoning_content (issue #487)
        assert message.content == [TextBlock(type="text", text="Hello")]
    else:
        assert message.content == [
            ThinkingBlock(
                type="thinking", thinking="Let me think", signature=""
            ),
            TextBlock(type="text", text="Hello"),
        ]


async def test_dial_only_chunks_are_dropped(stream: bool):
    async def _chat(request: Request, response: Response):
        with response.create_single_choice() as choice:
            with choice.create_stage("Searching the web") as stage:
                stage.append_content("Found 3 pages")
            choice.add_attachment(
                type="text/markdown", title="Report", data="# Report"
            )
            choice.append_content("Hello")
        response.add_usage_per_model("gpt-5.5", 1, 2)
        response.set_discarded_messages([0])

    async with _anthropic_client(_chat) as client:
        message = await client.final_message(stream=stream)

    assert message.content == [TextBlock(type="text", text="Hello")]


async def test_usage_is_split_into_anthropic_counters(stream: bool):
    async def _chat(request: Request, response: Response):
        with response.create_single_choice() as choice:
            choice.append_content("Hello")
        response.set_usage(
            prompt_tokens=10,
            completion_tokens=5,
            prompt_tokens_details={"cached_tokens": 4, "cache_write_tokens": 2},
            completion_tokens_details={"reasoning_tokens": 3},
        )

    async with _anthropic_client(_chat) as client:
        message = await client.final_message(stream=stream)

    assert message.usage == Usage(
        input_tokens=4,
        output_tokens=5,
        cache_read_input_tokens=4,
        cache_creation_input_tokens=2,
        output_tokens_details=OutputTokensDetails(thinking_tokens=3),
    )


@pytest.mark.parametrize(
    "finish_reason, stop_reason",
    [
        (FinishReason.STOP, "end_turn"),
        (FinishReason.LENGTH, "max_tokens"),
        (FinishReason.CONTENT_FILTER, "refusal"),
    ],
)
async def test_finish_reason_is_a_stop_reason(
    stream: bool, finish_reason: FinishReason, stop_reason: str
):
    async def _chat(request: Request, response: Response):
        choice = response.create_single_choice()
        choice.open()
        choice.append_content("Hello")
        choice.close(finish_reason)

    async with _anthropic_client(_chat) as client:
        message = await client.final_message(stream=stream)

    assert message.stop_reason == stop_reason


def _describe(event: RawMessageStreamEvent) -> str:
    match event.type:
        case "content_block_start":
            return f"{event.type} {event.index} {event.content_block.type}"
        case "content_block_delta":
            return f"{event.type} {event.index} {event.delta.type}"
        case "content_block_stop":
            return f"{event.type} {event.index}"
        case "message_delta":
            return f"{event.type} {event.delta.stop_reason}"
        case _:
            return event.type


async def test_stream_events_of_text_followed_by_a_tool_call():
    async def _chat(request: Request, response: Response):
        with response.create_single_choice() as choice:
            choice.append_content("Let me check")
            choice.create_function_tool_call(
                id="call_1", name="get_weather", arguments='{"city": "Paris"}'
            )

    async with _anthropic_client(_chat) as client:
        stream = await client.stream_events(tools=[_WEATHER_TOOL])
        events = [event async for event in stream]

    assert [_describe(event) for event in events] == [
        "message_start",
        "content_block_start 0 text",
        "content_block_delta 0 text_delta",
        "content_block_stop 0",
        "content_block_start 1 tool_use",
        "content_block_delta 1 input_json_delta",
        "content_block_stop 1",
        "message_delta tool_use",
        "message_stop",
    ]
