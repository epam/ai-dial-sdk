import json
from datetime import UTC, datetime
from typing import cast

import pytest
from anthropic.types.beta.message_create_params import MessageCreateParams

from aidial_sdk.chat_completion.request import (
    CacheBreakpoint,
    FunctionChoice,
    ImageURL,
    InputFile,
    MessageContentFilePart,
    MessageContentImagePart,
    MessageContentTextPart,
    Role,
    ToolChoice,
)
from aidial_sdk.chat_completion.request import (
    Tool as SdkTool,
)
from aidial_sdk.translators.messages_to_chat_completions.chat_completions.to_chat_completions import (
    to_chat_completions_request,
)
from aidial_sdk.translators.messages_to_chat_completions.errors import (
    AnthropicErrorType,
    AnthropicHTTPError,
)
from aidial_sdk.translators.messages_to_chat_completions.translation_state import (
    TranslationState,
)
from tests.translators.messages_to_chat_completions.helpers import (
    DEPLOYMENT,
    convert,
    user,
)

LONG_MCP_NAME = "mcp__" + "s" * 60 + "__do_the_thing"


@pytest.mark.parametrize("max_tokens", [100, 999999])
def test_minimal_request(max_tokens: int) -> None:
    result = convert({**user("hello"), "max_tokens": max_tokens})
    assert result.model_dump(mode="json", exclude_none=True) == {
        "model": DEPLOYMENT,
        "messages": [{"role": "user", "content": "hello"}],
        "max_completion_tokens": max_tokens,
        "stream": False,
    }


def test_system_string() -> None:
    result = convert({"system": "be nice", **user("hi")})
    assert result.messages[0].role == Role.SYSTEM
    assert result.messages[0].content == "be nice"


def test_system_blocks_joined_and_cache_control_stripped() -> None:
    result = convert(
        {
            "system": [
                {
                    "type": "text",
                    "text": "a",
                    "cache_control": {"type": "ephemeral"},
                },
                {"type": "text", "text": "b"},
            ],
            **user("hi"),
        }
    )
    assert result.messages[0].role == Role.SYSTEM
    assert result.messages[0].content == "a\n\nb"

    assert "cache_control" not in result.model_dump_json(exclude_none=True)

    assert result.messages[0].custom_fields is not None
    assert result.messages[0].custom_fields.cache_breakpoint is not None


def test_all_three_system_sources_merge_into_one_leading_message() -> None:
    result = convert(
        {
            "system": "be nice",
            "messages": [
                {"role": "system", "content": "hook context"},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "mid_conv_system",
                            "content": [{"type": "text", "text": "injected"}],
                        },
                        {"type": "text", "text": "hi"},
                    ],
                },
            ],
        }
    )
    system_messages = [m for m in result.messages if m.role == Role.SYSTEM]
    assert len(system_messages) == 1
    assert system_messages[0].content == "be nice\n\nhook context\n\ninjected"
    assert system_messages[0] is result.messages[0]


def test_system_sources_merge_in_client_order_not_grouped_by_kind() -> None:
    result = convert(
        {
            "system": "TOP",
            "messages": [
                {"role": "system", "content": "A"},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "mid_conv_system",
                            "content": [{"type": "text", "text": "B"}],
                        },
                        {"type": "text", "text": "hi"},
                    ],
                },
                {"role": "system", "content": "C"},
            ],
        }
    )
    assert result.messages[0].content == "TOP\n\nA\n\nB\n\nC"


def test_mid_conv_system_on_an_assistant_message_is_merged_not_warned() -> None:
    result = convert(
        {
            "messages": [
                {"role": "user", "content": "hi"},
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "mid_conv_system",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "from the assistant turn",
                                }
                            ],
                        },
                        {"type": "text", "text": "hello"},
                    ],
                },
            ]
        }
    )
    assert result.messages[0].role == Role.SYSTEM
    assert result.messages[0].content == "from the assistant turn"
    assert result.messages[2].content == "hello"


def test_mid_conv_system_inside_a_system_role_message() -> None:
    result = convert(
        {
            "messages": [
                {
                    "role": "system",
                    "content": [
                        {"type": "text", "text": "outer"},
                        {
                            "type": "mid_conv_system",
                            "content": [{"type": "text", "text": "inner"}],
                        },
                    ],
                },
                {"role": "user", "content": "hi"},
            ]
        }
    )
    assert result.messages[0].content == "outer\n\ninner"


def test_mid_conv_system_cache_control_marks_the_merged_message() -> None:
    result = convert(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "mid_conv_system",
                            "content": [{"type": "text", "text": "ctx"}],
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                }
            ]
        }
    )
    assert result.messages[0].custom_fields is not None
    assert result.messages[0].custom_fields.cache_breakpoint is not None


def test_unsupported_system_role_content_block_is_dropped() -> None:
    result = convert(
        {
            "messages": [
                {
                    "role": "system",
                    "content": [
                        {"type": "text", "text": "keep me"},
                        {
                            "type": "image",
                            "source": {
                                "type": "url",
                                "url": "https://example.com/image.png",
                            },
                        },
                    ],
                },
                {"role": "user", "content": "hi"},
            ]
        }
    )
    system_messages = [m for m in result.messages if m.role == Role.SYSTEM]
    assert len(system_messages) == 1
    assert system_messages[0].content == "keep me"


def test_base64_image() -> None:
    result = convert(
        user(
            [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": "QUJD",
                    },
                }
            ]
        )
    )
    content = result.messages[0].content
    assert isinstance(content, list)
    assert content[0] == MessageContentImagePart(
        type="image_url",
        image_url=ImageURL(url="data:image/jpeg;base64,QUJD"),
    )


def test_url_image() -> None:
    result = convert(
        user(
            [
                {
                    "type": "image",
                    "source": {"type": "url", "url": "https://x/y.png"},
                }
            ]
        )
    )
    content = result.messages[0].content
    assert isinstance(content, list)
    assert content[0] == MessageContentImagePart(
        type="image_url", image_url=ImageURL(url="https://x/y.png")
    )


def test_pdf_document_base64() -> None:
    result = convert(
        user(
            [
                {
                    "type": "document",
                    "title": "report.pdf",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": "UERG",
                    },
                }
            ]
        )
    )
    content = result.messages[0].content
    assert isinstance(content, list)
    assert content[0] == MessageContentFilePart(
        type="file",
        file=InputFile(
            filename="report.pdf",
            file_data="data:application/pdf;base64,UERG",
        ),
    )


@pytest.mark.parametrize(
    "source",
    [
        {"type": "url", "url": "https://x/y.pdf"},
        {"type": "file", "file_id": "f1"},
    ],
)
def test_document_url_or_file_source_is_rejected(
    source: dict[str, object],
) -> None:
    with pytest.raises(AnthropicHTTPError) as error:
        convert(user([{"type": "document", "source": source}]))
    assert error.value.error_type == AnthropicErrorType.INVALID_REQUEST


def test_document_content_source_becomes_its_text_and_image_parts() -> None:
    result = convert(
        user(
            [
                {
                    "type": "document",
                    "source": {
                        "type": "content",
                        "content": [
                            {"type": "text", "text": "page one"},
                            {
                                "type": "image",
                                "source": {
                                    "type": "url",
                                    "url": "https://x/p.png",
                                },
                            },
                        ],
                    },
                }
            ]
        )
    )
    assert result.messages[0].content == [
        MessageContentTextPart(type="text", text="page one"),
        MessageContentImagePart(
            type="image_url", image_url=ImageURL(url="https://x/p.png")
        ),
    ]


def test_search_result_becomes_a_text_part() -> None:
    result = convert(
        user(
            [
                {
                    "type": "search_result",
                    "title": "Cats",
                    "source": "https://e.com/cats",
                    "content": [
                        {"type": "text", "text": "Cats purr."},
                        {"type": "text", "text": "Cats nap."},
                    ],
                }
            ]
        )
    )
    assert result.messages[0].content == [
        MessageContentTextPart(
            type="text",
            text="Cats\nhttps://e.com/cats\n\nCats purr.\nCats nap.",
        )
    ]


def test_replayed_compaction_becomes_its_summary_text() -> None:
    result = convert(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "compaction", "content": "earlier summary"},
                        {"type": "text", "text": "go on"},
                    ],
                },
                {
                    "role": "assistant",
                    "content": [
                        {"type": "compaction", "content": "assistant summary"},
                        {"type": "compaction", "content": None},
                        {"type": "text", "text": "ok"},
                    ],
                },
            ]
        }
    )
    assert result.messages[0].content == [
        MessageContentTextPart(type="text", text="earlier summary"),
        MessageContentTextPart(type="text", text="go on"),
    ]
    assert result.messages[1].content == "assistant summary\nok"


def test_document_text_source_becomes_text_part() -> None:
    result = convert(
        user(
            [
                {
                    "type": "document",
                    "source": {
                        "type": "text",
                        "media_type": "text/plain",
                        "data": "inline document text",
                    },
                }
            ]
        )
    )
    content = result.messages[0].content
    assert isinstance(content, list)
    assert content[0] == MessageContentTextPart(
        type="text", text="inline document text"
    )


def test_image_file_source_is_rejected() -> None:
    with pytest.raises(AnthropicHTTPError) as error:
        convert(
            user(
                [{"type": "image", "source": {"type": "file", "file_id": "f1"}}]
            )
        )
    assert error.value.error_type == AnthropicErrorType.INVALID_REQUEST


def test_assistant_tool_use_and_text_combine_into_one_message() -> None:
    result = convert(
        {
            "messages": [
                {"role": "user", "content": "search"},
                {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "let me look"},
                        {
                            "type": "tool_use",
                            "id": "toolu_1",
                            "name": "search",
                            "input": {"q": "cats"},
                        },
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_1",
                            "content": "found cats",
                        },
                        {"type": "text", "text": "thanks"},
                    ],
                },
            ]
        }
    )
    messages = result.messages
    assert messages[1].role == Role.ASSISTANT
    assert messages[1].content == "let me look"
    tool_calls = messages[1].tool_calls
    assert tool_calls is not None
    assert len(tool_calls) == 1
    assert tool_calls[0].id == "toolu_1"
    assert tool_calls[0].type == "function"
    assert tool_calls[0].function.name == "search"
    assert tool_calls[0].function.arguments == json.dumps({"q": "cats"})

    assert messages[2].role == Role.TOOL
    assert messages[2].tool_call_id == "toolu_1"
    assert messages[2].content == "found cats"
    assert messages[3].role == Role.USER
    assert messages[3].content == [
        MessageContentTextPart(type="text", text="thanks")
    ]


def test_tool_result_only_turn_emits_no_user_message() -> None:
    result = convert(
        user(
            [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_1",
                    "content": "ok",
                }
            ]
        )
    )
    assert len(result.messages) == 1
    assert result.messages[0].role == Role.TOOL
    assert result.messages[0].tool_call_id == "toolu_1"
    assert result.messages[0].content == "ok"


def test_tool_result_is_error_prefixes_output() -> None:
    result = convert(
        user(
            [
                {
                    "type": "tool_result",
                    "tool_use_id": "t",
                    "content": "boom",
                    "is_error": True,
                }
            ]
        )
    )
    assert result.messages[0].content == "Error: boom"


def test_tool_result_image_becomes_user_image_url() -> None:
    result = convert(
        user(
            [
                {
                    "type": "tool_result",
                    "tool_use_id": "t",
                    "content": [
                        {"type": "text", "text": "see"},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": "AA",
                            },
                        },
                    ],
                }
            ]
        )
    )
    assert result.messages[0].role == Role.TOOL
    assert result.messages[0].content == "see"
    assert result.messages[1].content == [
        MessageContentImagePart(
            type="image_url",
            image_url=ImageURL(url="data:image/png;base64,AA"),
        )
    ]


def test_tool_result_document_moves_to_the_following_user_message() -> None:
    result = convert(
        user(
            [
                {
                    "type": "tool_result",
                    "tool_use_id": "t",
                    "content": [
                        {"type": "text", "text": "see file"},
                        {
                            "type": "document",
                            "title": "a.pdf",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": "UERG",
                            },
                        },
                    ],
                }
            ]
        )
    )
    assert result.messages[0].role == Role.TOOL
    assert result.messages[0].content == "see file"
    assert result.messages[1].content == [
        MessageContentFilePart(
            type="file",
            file=InputFile(
                filename="a.pdf", file_data="data:application/pdf;base64,UERG"
            ),
        )
    ]


def test_custom_tool_mapping() -> None:
    result = convert(
        {
            **user("hi"),
            "tools": [
                {
                    "name": "get_weather",
                    "description": "weather",
                    "input_schema": {"type": "object", "properties": {}},
                }
            ],
        }
    )
    tools = result.tools
    assert tools is not None
    tool = tools[0]
    assert isinstance(tool, SdkTool)
    assert tool.type == "function"
    assert tool.function.name == "get_weather"
    assert tool.function.parameters == {"type": "object", "properties": {}}

    assert tool.function.strict is False
    assert tool.function.description == "weather"
    assert tool.custom_fields is None


def test_custom_tool_strict_is_forwarded() -> None:
    result = convert(
        {
            **user("hi"),
            "tools": [
                {
                    "name": "get_weather",
                    "input_schema": {"type": "object"},
                    "strict": True,
                }
            ],
        }
    )
    assert result.model_dump(mode="json")["tools"][0]["function"]["strict"]


def test_schema_key_is_stripped_from_tool_parameters() -> None:
    result = convert(
        {
            **user("hi"),
            "tools": [
                {
                    "name": "get_weather",
                    "input_schema": {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "type": "object",
                        "properties": {"a": {"type": "string"}},
                    },
                }
            ],
        }
    )
    tools = result.tools
    assert tools is not None
    tool = tools[0]
    assert isinstance(tool, SdkTool)
    assert tool.function.parameters == {
        "type": "object",
        "properties": {"a": {"type": "string"}},
    }


def test_provider_tools_become_static_functions_as_sent() -> None:
    provider_tools: list[dict[str, object]] = [
        {
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 3,
            "cache_control": {"type": "ephemeral"},
        },
        {"type": "bash_20250124", "name": "bash"},
        {
            "type": "computer_20250124",
            "name": "computer",
            "display_width_px": 100,
            "display_height_px": 100,
        },
        {"type": "mcp_toolset", "mcp_server_name": "docs"},
    ]
    result = convert({**user("hi"), "tools": provider_tools})
    assert result.model_dump(mode="json", exclude_none=True)["tools"] == [
        {
            "type": "static_function",
            "static_function": {
                "name": tool.get("name") or tool["mcp_server_name"],
                "configuration": tool,
            },
        }
        for tool in provider_tools
    ]


@pytest.mark.parametrize(
    "tool_choice, expected",
    [
        ({"type": "auto"}, "auto"),
        ({"type": "any"}, "required"),
        ({"type": "none"}, "none"),
        (
            {"type": "tool", "name": "search"},
            ToolChoice(type="function", function=FunctionChoice(name="search")),
        ),
    ],
)
def test_tool_choice_matrix(
    tool_choice: dict[str, object], expected: str | ToolChoice | None
) -> None:
    result = convert({**user("hi"), "tool_choice": tool_choice})
    assert result.tool_choice == expected


def test_disable_parallel_tool_use_inverts() -> None:
    result = convert(
        {
            **user("hi"),
            "tool_choice": {"type": "auto", "disable_parallel_tool_use": True},
        }
    )
    assert result.tool_choice == "auto"
    assert result.parallel_tool_calls is False


def test_a_long_mcp_name_is_aliased_identically_at_all_three_sites() -> None:
    translation_state = TranslationState()
    result = convert(
        {
            "messages": [
                {"role": "user", "content": "hi"},
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "t1",
                            "name": LONG_MCP_NAME,
                            "input": {},
                        }
                    ],
                },
            ],
            "tools": [
                {"name": LONG_MCP_NAME, "input_schema": {"type": "object"}}
            ],
            "tool_choice": {"type": "tool", "name": LONG_MCP_NAME},
        },
        translation_state=translation_state,
    )
    tools = result.tools
    assert tools is not None
    tool = tools[0]
    assert isinstance(tool, SdkTool)
    alias = tool.function.name

    assert alias != LONG_MCP_NAME
    assert len(alias) <= 64
    tool_choice = result.tool_choice
    assert isinstance(tool_choice, ToolChoice)
    assert tool_choice.function.name == alias
    tool_calls = result.messages[1].tool_calls
    assert tool_calls is not None
    assert tool_calls[0].function.name == alias

    assert translation_state.to_client_tool_name(alias) == LONG_MCP_NAME


def test_no_cache_control_omits_cache_breakpoint() -> None:
    result = convert({"system": "be nice", **user("hi")})
    assert result.messages[0].custom_fields is None


def test_user_message_cache_control_marks_message() -> None:
    result = convert(
        user(
            [
                {
                    "type": "text",
                    "text": "hi",
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        )
    )
    assert result.messages[0].custom_fields is not None
    assert result.messages[0].custom_fields.cache_breakpoint is not None


def test_assistant_message_cache_control_marks_message() -> None:
    result = convert(
        {
            "messages": [
                {"role": "user", "content": "hi"},
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": "hello",
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                },
            ]
        }
    )
    assert result.messages[1].custom_fields is not None
    assert result.messages[1].custom_fields.cache_breakpoint is not None


def test_tool_result_turn_cache_control_marks_all_split_messages() -> None:
    result = convert(
        user(
            [
                {
                    "type": "tool_result",
                    "tool_use_id": "t",
                    "content": "found cats",
                    "cache_control": {"type": "ephemeral"},
                },
                {"type": "text", "text": "thanks"},
            ]
        )
    )
    assert result.messages[0].role == Role.TOOL
    assert result.messages[0].custom_fields is not None
    assert result.messages[1].role == Role.USER
    assert result.messages[1].custom_fields is not None


def test_a_block_ttl_reaches_the_marker_as_an_absolute_instant() -> None:
    result = convert(
        user(
            [
                {
                    "type": "text",
                    "text": "hi",
                    "cache_control": {"type": "ephemeral", "ttl": "1h"},
                }
            ]
        )
    )
    custom_fields = result.messages[0].custom_fields
    assert custom_fields is not None
    assert custom_fields.cache_breakpoint is not None
    assert custom_fields.cache_breakpoint.expire_at is not None


def test_the_longest_ttl_of_the_merged_system_sources_wins() -> None:
    result = convert(
        {
            "system": [
                {
                    "type": "text",
                    "text": "a",
                    "cache_control": {"type": "ephemeral", "ttl": "5m"},
                }
            ],
            "messages": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "text",
                            "text": "b",
                            "cache_control": {"type": "ephemeral", "ttl": "1h"},
                        }
                    ],
                },
                {"role": "user", "content": "hi"},
            ],
        }
    )
    custom_fields = result.messages[0].custom_fields
    assert custom_fields is not None
    assert custom_fields.cache_breakpoint is not None
    expire_at = custom_fields.cache_breakpoint.expire_at
    assert expire_at is not None
    remaining = datetime.fromisoformat(expire_at) - datetime.now(UTC)
    assert remaining.total_seconds() == pytest.approx(3600, abs=5)


def test_cache_control_nested_inside_a_tool_result_is_not_seen() -> None:
    result = convert(
        user(
            [
                {
                    "type": "tool_result",
                    "tool_use_id": "t",
                    "content": [
                        {
                            "type": "text",
                            "text": "found cats",
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                }
            ]
        )
    )
    assert result.messages[0].custom_fields is None


def test_tool_definition_cache_control_marks_tool() -> None:
    result = convert(
        {
            **user("hi"),
            "tools": [
                {
                    "name": "get_weather",
                    "input_schema": {"type": "object"},
                    "cache_control": {"type": "ephemeral"},
                }
            ],
        }
    )
    tools = result.tools
    assert tools is not None
    tool = tools[0]
    assert isinstance(tool, SdkTool)
    assert tool.custom_fields is not None
    assert tool.custom_fields.cache_breakpoint is not None


def test_temperature_and_top_p_pass_through() -> None:
    result = convert({**user("hi"), "temperature": 0.5, "top_p": 0.9})
    assert result.temperature == 0.5
    assert result.top_p == 0.9


def test_top_k_and_thinking_history_are_dropped() -> None:
    result = convert(
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "thinking",
                            "thinking": "secret",
                            "signature": "s",
                        },
                        {
                            "type": "redacted_thinking",
                            "data": "also secret",
                        },
                        {"type": "text", "text": "answer"},
                    ],
                }
            ],
            "top_k": 5,
        }
    )
    dumped = json.dumps(result.model_dump(mode="json", exclude_none=True))
    assert "top_k" not in dumped
    assert "secret" not in dumped
    assert result.messages[0].role == Role.ASSISTANT
    assert result.messages[0].content == "answer"


def test_fields_with_no_chat_completions_counterpart_are_dropped() -> None:
    result = convert(
        {
            **user("hi"),
            "mcp_servers": [
                {
                    "type": "url",
                    "name": "server",
                    "url": "https://example.com/mcp",
                }
            ],
            "container": {"id": "container_1"},
            "compaction": {"enabled": True},
            "inference_geo": "eu",
            "context_management": {
                "edits": [{"type": "clear_tool_uses_20250919"}]
            },
            "top_k": 40,
            "cache_control": {"type": "ephemeral"},
        }
    )
    dumped = json.dumps(result.model_dump(mode="json", exclude_none=True))
    for dropped in (
        "mcp_servers",
        "compaction",
        "container",
        "inference_geo",
        "context_management",
        "top_k",
        "cache_control",
    ):
        assert dropped not in dumped

    assert result.messages[0].content == "hi"


@pytest.mark.parametrize("user_id", ["u1", "u" * 65])
def test_user_id_is_forwarded_as_user(user_id: str) -> None:
    result = convert({**user("hi"), "metadata": {"user_id": user_id}})
    assert result.user == user_id


@pytest.mark.parametrize(
    "tier, expected",
    [("auto", "auto"), ("standard_only", "default"), ("priority", None)],
)
def test_service_tier_is_a_closed_table(
    tier: str, expected: str | None
) -> None:
    result = convert({**user("hi"), "service_tier": tier})
    assert result.service_tier == expected


def test_output_config_format_json_schema_converts() -> None:
    schema: dict[str, object] = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
        "additionalProperties": False,
    }
    result = convert(
        {
            **user("hi"),
            "output_config": {
                "format": {"type": "json_schema", "schema": schema}
            },
        }
    )
    assert result.response_format is not None
    assert result.response_format.type == "json_schema"
    assert result.response_format.json_schema.name == "response"
    assert result.response_format.json_schema.schema_ == schema

    assert result.response_format.json_schema.strict is True


def test_empty_output_schema_is_dropped() -> None:
    result = convert(
        {
            **user("hi"),
            "output_config": {"format": {"type": "json_schema", "schema": {}}},
        }
    )
    assert result.response_format is None


def test_citations_enabled_sets_custom_fields() -> None:
    result = convert(
        user(
            [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": "UERG",
                    },
                    "citations": {"enabled": True},
                }
            ]
        )
    )
    assert result.custom_fields is not None
    assert result.custom_fields.configuration == {"enable_citations": True}


@pytest.mark.parametrize("stop", [["STOP"], []])
def test_stop_sequences_map_to_stop_as_is(stop: list[str]) -> None:
    result = convert({**user("hi"), "stop_sequences": stop})
    assert result.model_dump(mode="json", exclude_none=True)["stop"] == stop


def test_absent_max_tokens_sends_no_cap_and_zero_is_sent() -> None:
    absent = to_chat_completions_request(
        cast(MessageCreateParams, {"model": DEPLOYMENT, **user("hi")}),
        DEPLOYMENT,
        TranslationState(),
    )
    assert "max_completion_tokens" not in absent.model_dump(exclude_none=True)
    assert convert({**user("hi"), "max_tokens": 0}).max_completion_tokens == 0


def test_an_unknown_role_is_rejected() -> None:
    with pytest.raises(AnthropicHTTPError) as error:
        convert({"messages": [{"role": "developer", "content": "hi"}]})
    assert error.value.error_type == AnthropicErrorType.INVALID_REQUEST


def test_a_system_turn_cleared_at_the_next_user_message() -> None:
    result = convert(
        {
            "messages": [
                {"role": "user", "content": "one"},
                {
                    "role": "system",
                    "content": "cleared",
                    "clear_at": "next_user_message",
                },
                {"role": "system", "content": "kept", "clear_at": "never"},
                {"role": "user", "content": "two"},
                {
                    "role": "system",
                    "content": "still visible",
                    "clear_at": "next_user_message",
                },
            ]
        }
    )
    assert result.messages[0].role == Role.SYSTEM
    assert result.messages[0].content == "kept\n\nstill visible"


def test_top_level_cache_control_becomes_the_request_breakpoint() -> None:
    result = convert(
        {
            "messages": [
                *user("hi")["messages"],
                {"role": "assistant", "content": "prefill"},
            ],
            "cache_control": {"type": "ephemeral"},
        }
    )
    assert all(m.custom_fields is None for m in result.messages)
    assert result.custom_fields is not None
    assert result.custom_fields.cache_breakpoint == CacheBreakpoint()


def test_top_level_cache_control_ttl_sets_the_request_expiry() -> None:
    result = convert(
        {**user("hi"), "cache_control": {"type": "ephemeral", "ttl": "5m"}}
    )
    fields = result.custom_fields
    assert (
        fields and fields.cache_breakpoint and fields.cache_breakpoint.expire_at
    )
    seconds = (
        datetime.fromisoformat(fields.cache_breakpoint.expire_at)
        - datetime.now(UTC)
    ).total_seconds()
    assert seconds == pytest.approx(300, abs=2)


def test_null_block_cache_control_does_not_mark() -> None:
    result = convert(
        user(
            [
                {
                    "type": "text",
                    "text": "hi",
                    "cache_control": None,
                }
            ]
        )
    )
    assert result.messages[0].custom_fields is None


def test_tool_schema_keywords_are_preserved() -> None:
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "additionalProperties": False,
        "$defs": {"name": {"type": "string"}},
        "oneOf": [{"required": ["name"]}],
    }
    result = convert(
        {**user("hi"), "tools": [{"name": "test_tool", "input_schema": schema}]}
    )
    assert result.model_dump()["tools"][0]["function"]["parameters"] == schema
