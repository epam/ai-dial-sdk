from typing import Literal

import pytest
from anthropic.types import (
    Message,
    ServerToolUseBlock,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    WebSearchToolResultBlock,
)
from anthropic.types.output_tokens_details import OutputTokensDetails
from openai.types.chat import ChatCompletion
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from openai.types.chat.chat_completion_message_custom_tool_call import (
    ChatCompletionMessageCustomToolCall,
    Custom,
)
from openai.types.chat.chat_completion_message_function_tool_call import (
    ChatCompletionMessageFunctionToolCall,
    Function,
)
from openai.types.completion_usage import (
    CompletionTokensDetails,
    CompletionUsage,
    PromptTokensDetails,
)

from aidial_sdk.translators.messages_to_chat_completions.chat_completions.from_chat_completions import (
    to_anthropic_response,
    to_anthropic_stop_reason,
)
from aidial_sdk.translators.messages_to_chat_completions.translation_state import (
    TranslationState,
)

FinishReason = Literal[
    "stop", "length", "tool_calls", "content_filter", "function_call"
]

LONG_MCP_NAME = "mcp__" + "s" * 60 + "__do_the_thing"


def message(**fields: object) -> ChatCompletionMessage:
    return ChatCompletionMessage.model_validate(
        {"role": "assistant", "content": None, **fields}
    )


def response(
    msg: ChatCompletionMessage | None = None,
    finish_reason: FinishReason = "stop",
    model: str = "gpt-5.5",
    usage: CompletionUsage | None = None,
) -> ChatCompletion:
    return ChatCompletion(
        id="chatcmpl_abc",
        object="chat.completion",
        created=0,
        model=model,
        choices=[
            Choice(
                index=0,
                message=msg if msg is not None else message(),
                finish_reason=finish_reason,
            )
        ],
        usage=usage
        or CompletionUsage(
            prompt_tokens=10, completion_tokens=5, total_tokens=15
        ),
    )


def translate(
    completion: ChatCompletion,
    translation_state: TranslationState | None = None,
) -> Message:
    return to_anthropic_response(
        completion,
        "requested-model",
        translation_state or TranslationState(),
    )


def tool_call(
    name: str = "search", arguments: str = '{"q": "cats"}', id: str = "toolu_1"
) -> ChatCompletionMessageFunctionToolCall:
    return ChatCompletionMessageFunctionToolCall(
        id=id,
        type="function",
        function=Function(name=name, arguments=arguments),
    )


def test_text_output() -> None:
    msg = translate(response(message(content="hello")))
    assert msg.id == "chatcmpl_abc"
    assert msg.type == "message"
    assert msg.role == "assistant"
    assert msg.model == "requested-model"
    assert msg.content == [TextBlock(type="text", text="hello")]
    assert msg.stop_reason == "end_turn"
    assert msg.stop_sequence is None


def test_model_falls_back_to_requested() -> None:
    assert translate(response(model="")).model == "requested-model"


def test_only_first_choice_translated() -> None:
    completion = response(message(content="first"))
    completion.choices.append(
        Choice(
            index=1,
            message=message(content="second"),
            finish_reason="stop",
        )
    )
    assert translate(completion).content == [
        TextBlock(type="text", text="first")
    ]


@pytest.mark.parametrize(
    "completion",
    [
        response(message(content="")),
        response(message(content=None)),
        ChatCompletion(
            id="c",
            object="chat.completion",
            created=0,
            model="gpt-5.5",
            choices=[],
        ),
    ],
)
def test_an_empty_completion_yields_one_empty_text_block(
    completion: ChatCompletion,
) -> None:
    assert translate(completion).content == [TextBlock(type="text", text="")]


def test_signed_thinking_from_state_leads_the_content() -> None:
    msg = translate(
        response(
            message(
                content="the answer",
                custom_content={
                    "state": {
                        "claude_message_content": [
                            {
                                "type": "thinking",
                                "thinking": "let me think",
                                "signature": "sig-abc",
                            }
                        ]
                    }
                },
            )
        )
    )
    assert msg.content[0] == ThinkingBlock(
        type="thinking", thinking="let me think", signature="sig-abc"
    )
    assert msg.content[1] == TextBlock(type="text", text="the answer")


def test_thinking_from_reasoning_stages_has_an_empty_signature() -> None:
    msg = translate(
        response(
            message(
                content="answer",
                custom_content={
                    "stages": [
                        {"index": 0, "name": "Thinking", "content": "a"},
                        {"index": 1, "name": "Searching", "content": "ignored"},
                        {"index": 2, "name": "Reasoning", "content": "b"},
                    ]
                },
            )
        )
    )

    assert msg.content[0] == ThinkingBlock(
        type="thinking", thinking="ab", signature=""
    )


def test_state_thinking_is_preferred_over_stages() -> None:
    msg = translate(
        response(
            message(
                custom_content={
                    "stages": [
                        {"index": 0, "name": "Thinking", "content": "stage"}
                    ],
                    "state": {
                        "claude_message_content": [
                            {
                                "type": "thinking",
                                "thinking": "signed",
                                "signature": "s",
                            }
                        ]
                    },
                },
            )
        )
    )
    assert msg.content[0] == ThinkingBlock(
        type="thinking", thinking="signed", signature="s"
    )


@pytest.mark.parametrize(
    "name", ["Thinking", "thought process", "Reasoning", "REASON", "Thoughts"]
)
def test_a_reasoning_stage_is_recognised_by_substring(name: str) -> None:
    msg = translate(
        response(
            message(
                custom_content={
                    "stages": [{"index": 0, "name": name, "content": "t"}]
                }
            )
        )
    )
    assert msg.content[0] == ThinkingBlock(
        type="thinking", thinking="t", signature=""
    )


def test_custom_content_without_reasoning_adds_no_thinking_block() -> None:
    msg = translate(
        response(
            message(
                content="hi",
                custom_content={
                    "stages": [
                        {"index": 0, "name": "Searching", "content": "x"}
                    ]
                },
            )
        )
    )
    assert msg.content == [TextBlock(type="text", text="hi")]


def test_malformed_custom_content_is_ignored() -> None:
    msg = translate(response(message(content="hi", custom_content="nonsense")))
    assert msg.content == [TextBlock(type="text", text="hi")]


@pytest.mark.parametrize(
    "urls",
    [["https://example.com"], ["https://example.com", "https://second.com"]],
)
def test_url_citations_become_a_server_tool_use_pair(urls: list[str]) -> None:
    msg = translate(
        response(
            message(
                content="answer",
                annotations=[
                    {
                        "type": "url_citation",
                        "url_citation": {
                            "url": url,
                            "title": "Example",
                            "start_index": 0,
                            "end_index": 1,
                        },
                    }
                    for url in urls
                ],
            )
        )
    )
    use, result, text = msg.content
    assert isinstance(use, ServerToolUseBlock)
    assert isinstance(result, WebSearchToolResultBlock)
    assert use.name == "web_search"
    assert use.id.startswith("srvtoolu_")

    assert result.tool_use_id == use.id
    assert isinstance(result.content, list)
    assert [item.url for item in result.content] == urls
    assert result.content[0].title == "Example"
    assert text == TextBlock(type="text", text="answer")


def test_tool_call_becomes_tool_use() -> None:
    msg = translate(
        response(message(tool_calls=[tool_call()]), finish_reason="tool_calls")
    )
    block = msg.content[0]
    assert isinstance(block, ToolUseBlock)
    assert block.id == "toolu_1"
    assert block.name == "search"
    assert block.input == {"q": "cats"}
    assert msg.stop_reason == "tool_use"


def test_an_aliased_tool_name_is_restored() -> None:
    translation_state = TranslationState()
    alias = translation_state.to_upstream_tool_name(LONG_MCP_NAME)
    msg = translate(
        response(message(tool_calls=[tool_call(name=alias)])), translation_state
    )
    block = msg.content[0]
    assert isinstance(block, ToolUseBlock)
    assert block.name == LONG_MCP_NAME


@pytest.mark.parametrize(
    "finish_reason, expected",
    [("length", "max_tokens"), ("content_filter", "refusal")],
)
def test_a_cut_off_or_filtered_finish_wins_over_tool_calls(
    finish_reason: FinishReason, expected: str
) -> None:
    msg = translate(
        response(message(tool_calls=[tool_call()]), finish_reason=finish_reason)
    )
    assert msg.stop_reason == expected


def test_tool_calls_win_the_stop_reason_over_the_finish_reason() -> None:
    msg = translate(
        response(message(tool_calls=[tool_call()]), finish_reason="stop")
    )
    assert msg.stop_reason == "tool_use"


@pytest.mark.parametrize("arguments", ["[1, 2, 3]", "{not json", ""])
def test_unusable_tool_arguments_become_an_empty_input(arguments: str) -> None:
    msg = translate(
        response(message(tool_calls=[tool_call(arguments=arguments)]))
    )
    block = msg.content[0]
    assert isinstance(block, ToolUseBlock)
    assert block.input == {}


def test_a_non_function_tool_call_is_skipped() -> None:
    msg = translate(
        response(
            message(
                content="hi",
                tool_calls=[
                    ChatCompletionMessageCustomToolCall(
                        id="x", type="custom", custom=Custom(name="f", input="")
                    )
                ],
            )
        )
    )
    assert msg.content == [TextBlock(type="text", text="hi")]
    assert msg.stop_reason == "end_turn"


def test_refusal_sets_stop_reason_refusal() -> None:
    msg = translate(response(message(refusal="no")))
    assert msg.content == [TextBlock(type="text", text="no")]
    assert msg.stop_reason == "refusal"


@pytest.mark.parametrize(
    "finish_reason, expected",
    [
        ("length", "max_tokens"),
        ("content_filter", "refusal"),
        ("stop", "end_turn"),
    ],
)
def test_stop_reason_mapping(
    finish_reason: FinishReason, expected: str
) -> None:
    msg = translate(response(message(content="x"), finish_reason=finish_reason))

    assert msg.stop_reason == expected


@pytest.mark.parametrize("finish_reason", [None, "bogus"])
def test_an_unrecognised_finish_reason_falls_back_to_end_turn(
    finish_reason: str | None,
) -> None:
    assert (
        to_anthropic_stop_reason(
            finish_reason, has_tool_call=False, is_refusal=False
        )
        == "end_turn"
    )


def test_cached_tokens_are_subtracted_from_input_tokens() -> None:
    msg = translate(
        response(
            usage=CompletionUsage(
                prompt_tokens=100,
                completion_tokens=20,
                total_tokens=120,
                prompt_tokens_details=PromptTokensDetails(cached_tokens=30),
            )
        )
    )
    assert msg.usage.input_tokens == 70
    assert msg.usage.output_tokens == 20
    assert msg.usage.cache_read_input_tokens == 30
    assert msg.usage.cache_creation_input_tokens == 0


def test_usage_without_cache_details() -> None:
    msg = translate(
        response(
            usage=CompletionUsage(
                prompt_tokens=10, completion_tokens=5, total_tokens=15
            )
        )
    )
    assert msg.usage.input_tokens == 10
    assert msg.usage.cache_read_input_tokens == 0
    assert msg.usage.cache_creation_input_tokens == 0


def test_cache_counters_are_capped_at_prompt_tokens() -> None:
    msg = translate(
        response(
            usage=CompletionUsage(
                prompt_tokens=5,
                completion_tokens=1,
                total_tokens=6,
                prompt_tokens_details=PromptTokensDetails.model_validate(
                    {"cached_tokens": 4, "cache_write_tokens": 3}
                ),
            )
        )
    )
    assert msg.usage.input_tokens == 0
    assert msg.usage.cache_read_input_tokens == 4
    assert msg.usage.cache_creation_input_tokens == 1


def test_missing_usage_is_zeroed_not_an_error() -> None:
    completion = response()
    completion.usage = None
    usage = translate(completion).usage
    assert usage.input_tokens == 0
    assert usage.output_tokens == 0


def test_cache_writes_are_recovered_and_subtracted() -> None:
    msg = translate(
        response(
            usage=CompletionUsage(
                prompt_tokens=100,
                completion_tokens=20,
                total_tokens=120,
                prompt_tokens_details=PromptTokensDetails.model_validate(
                    {"cached_tokens": 30, "cache_write_tokens": 25}
                ),
            )
        )
    )
    assert msg.usage.input_tokens == 45
    assert msg.usage.cache_read_input_tokens == 30
    assert msg.usage.cache_creation_input_tokens == 25


def test_reasoning_tokens_become_an_informational_breakdown() -> None:
    msg = translate(
        response(
            usage=CompletionUsage(
                prompt_tokens=10,
                completion_tokens=50,
                total_tokens=60,
                completion_tokens_details=CompletionTokensDetails(
                    reasoning_tokens=40
                ),
            )
        )
    )
    assert msg.usage.output_tokens == 50
    assert msg.usage.output_tokens_details == OutputTokensDetails(
        thinking_tokens=40
    )


def test_zero_reasoning_tokens_emit_a_zero_breakdown() -> None:
    msg = translate(
        response(
            usage=CompletionUsage(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                completion_tokens_details=CompletionTokensDetails(
                    reasoning_tokens=0
                ),
            )
        )
    )
    assert msg.usage.output_tokens_details == OutputTokensDetails(
        thinking_tokens=0
    )


def test_full_block_order() -> None:
    msg = translate(
        response(
            message(
                content="text",
                refusal="refused",
                custom_content={
                    "stages": [{"index": 0, "name": "Thinking", "content": "t"}]
                },
                annotations=[
                    {
                        "type": "url_citation",
                        "url_citation": {
                            "url": "https://e.com",
                            "title": "E",
                            "start_index": 0,
                            "end_index": 1,
                        },
                    }
                ],
                tool_calls=[tool_call()],
            )
        )
    )
    assert [block.type for block in msg.content] == [
        "thinking",
        "server_tool_use",
        "web_search_tool_result",
        "text",
        "text",
        "tool_use",
    ]
