import logging

import pytest

from aidial_sdk.exceptions import InvalidRequestError
from aidial_sdk.translators._messages.translation_state import (
    TranslationState,
)
from tests.translators.messages_to_responses.helpers import (
    LONG_MCP_ALIAS,
    LONG_MCP_NAME,
    MODEL,
    convert,
    signature,
    user,
)

_FILES_API_UNSUPPORTED = (
    "Files uploaded via Anthropic Files API aren't supported."
)


def test_minimal_request() -> None:
    assert convert({"max_tokens": 100, **user("Hi")}) == {
        "model": MODEL,
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Hi"}],
            }
        ],
        "max_output_tokens": 100,
        "store": False,
        "include": ["reasoning.encrypted_content"],
        "stream": False,
    }


def test_stream() -> None:
    assert convert({"stream": True, **user("Hi")})["stream"] is True


@pytest.mark.parametrize(
    "max_tokens, max_output_tokens",
    [(1, 16), (15, 16), (16, 16), (1000, 1000), (0, 0)],
    ids=["probe", "below-minimum", "minimum", "above-minimum", "zero"],
)
def test_max_tokens_is_raised_to_the_responses_minimum(
    max_tokens: int, max_output_tokens: int
) -> None:
    request = convert({"max_tokens": max_tokens, **user("Hi")})
    assert request["max_output_tokens"] == max_output_tokens


def test_absent_max_tokens_sends_no_cap() -> None:
    assert "max_output_tokens" not in convert(user("Hi"))


def test_empty_user_text_sends_nothing() -> None:
    assert convert(user(""))["input"] == []


class TestSystem:
    def test_string_becomes_instructions(self) -> None:
        assert convert({"system": "Be brief", **user("Hi")})[
            "instructions"
        ] == ("Be brief")

    def test_text_blocks_are_joined(self) -> None:
        request = convert(
            {
                "system": [
                    {"type": "text", "text": "One"},
                    {"type": "text", "text": "Two"},
                ],
                **user("Hi"),
            }
        )
        assert request["instructions"] == "One\n\nTwo"

    def test_empty_system_sends_no_instructions(self) -> None:
        assert "instructions" not in convert({"system": "", **user("Hi")})

    def test_system_turn_stays_in_place(self) -> None:
        request = convert(
            {
                "messages": [
                    {"role": "user", "content": "Hi"},
                    {"role": "system", "content": "Answer in French"},
                    {"role": "user", "content": "Bye"},
                ]
            }
        )
        assert [
            (item["role"], item["content"]) for item in request["input"]
        ] == [
            ("user", [{"type": "input_text", "text": "Hi"}]),
            ("system", [{"type": "input_text", "text": "Answer in French"}]),
            ("user", [{"type": "input_text", "text": "Bye"}]),
        ]

    def test_expired_system_turn_isnt_sent(self) -> None:
        request = convert(
            {
                "messages": [
                    {
                        "role": "system",
                        "content": "Hook context",
                        "clear_at": "next_user_message",
                    },
                    {"role": "user", "content": "Hi"},
                ]
            }
        )
        assert [item["role"] for item in request["input"]] == ["user"]

    def test_mid_conv_system_follows_the_tool_outputs_of_a_user_turn(
        self,
    ) -> None:
        request = convert(
            user(
                [
                    {"type": "text", "text": "Go on"},
                    {
                        "type": "mid_conv_system",
                        "content": [{"type": "text", "text": "Hook"}],
                    },
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_1",
                        "content": "42",
                    },
                ]
            )
        )
        assert request["input"] == [
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": "42",
            },
            {
                "type": "message",
                "role": "system",
                "content": [{"type": "input_text", "text": "Hook"}],
            },
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Go on"}],
            },
        ]

    def test_mid_conv_system_precedes_its_assistant_turn(self) -> None:
        request = convert(
            {
                "messages": [
                    {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": "Calling"},
                            {
                                "type": "mid_conv_system",
                                "content": [{"type": "text", "text": "Hook"}],
                            },
                        ],
                    }
                ]
            }
        )
        assert [item["role"] for item in request["input"]] == [
            "system",
            "assistant",
        ]


def test_unknown_role_is_rejected() -> None:
    with pytest.raises(InvalidRequestError) as e:
        convert({"messages": [{"role": "robot", "content": "Hi"}]})
    assert e.value.message == "Unsupported message role: robot"


class TestContentBlocks:
    def test_base64_image(self) -> None:
        request = convert(
            user(
                [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": "AAAA",
                        },
                    }
                ]
            )
        )
        assert request["input"][0]["content"] == [
            {
                "type": "input_image",
                "image_url": "data:image/jpeg;base64,AAAA",
                "detail": "auto",
            }
        ]

    def test_url_image(self) -> None:
        request = convert(
            user(
                [
                    {
                        "type": "image",
                        "source": {"type": "url", "url": "https://x/a.png"},
                    }
                ]
            )
        )
        assert request["input"][0]["content"] == [
            {
                "type": "input_image",
                "image_url": "https://x/a.png",
                "detail": "auto",
            }
        ]

    @pytest.mark.parametrize("block_type", ["image", "document"])
    def test_files_api_source_is_rejected(self, block_type: str) -> None:
        with pytest.raises(InvalidRequestError) as e:
            convert(
                user(
                    [
                        {
                            "type": block_type,
                            "source": {"type": "file", "file_id": "file_1"},
                        }
                    ]
                )
            )
        assert e.value.message == _FILES_API_UNSUPPORTED

    @pytest.mark.parametrize(
        "source, parts",
        [
            (
                {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": "JVBE",
                },
                [
                    {
                        "type": "input_file",
                        "filename": "report.pdf",
                        "file_data": "data:application/pdf;base64,JVBE",
                    }
                ],
            ),
            (
                {"type": "url", "url": "https://x/report.pdf"},
                [{"type": "input_file", "file_url": "https://x/report.pdf"}],
            ),
            (
                {"type": "text", "media_type": "text/plain", "data": "Plain"},
                [{"type": "input_text", "text": "Plain"}],
            ),
            (
                {
                    "type": "content",
                    "content": [{"type": "text", "text": "Inner"}],
                },
                [{"type": "input_text", "text": "Inner"}],
            ),
        ],
        ids=["base64", "url", "text", "content"],
    )
    def test_document(
        self, source: dict[str, object], parts: list[dict[str, object]]
    ) -> None:
        request = convert(
            user(
                [{"type": "document", "title": "report.pdf", "source": source}]
            )
        )
        assert request["input"][0]["content"] == parts

    def test_search_result_becomes_text(self) -> None:
        request = convert(
            user(
                [
                    {
                        "type": "search_result",
                        "title": "Title",
                        "source": "https://x",
                        "content": [{"type": "text", "text": "Body"}],
                    }
                ]
            )
        )
        assert request["input"][0]["content"] == [
            {"type": "input_text", "text": "Title\nhttps://x\n\nBody"}
        ]

    def test_unsupported_block_is_dropped_with_a_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            request = convert(
                user(
                    [
                        {"type": "text", "text": "Hi"},
                        {"type": "container_upload", "file_id": "file_1"},
                    ]
                )
            )
        assert request["input"][0]["content"] == [
            {"type": "input_text", "text": "Hi"}
        ]
        assert caplog.messages == [
            "Dropping unsupported content block: container_upload"
        ]


class TestToolResult:
    @pytest.mark.parametrize(
        "is_error, output",
        [(False, "a\nb"), (True, "Error: a\nb")],
        ids=["success", "error"],
    )
    def test_text_becomes_a_string(self, is_error: bool, output: str) -> None:
        request = convert(
            user(
                [
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_1",
                        "is_error": is_error,
                        "content": [
                            {"type": "text", "text": "a"},
                            {"type": "text", "text": "b"},
                        ],
                    }
                ]
            )
        )
        assert request["input"] == [
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": output,
            }
        ]

    @pytest.mark.parametrize(
        "is_error, prefix",
        [(False, []), (True, [{"type": "input_text", "text": "Error:"}])],
        ids=["success", "error"],
    )
    def test_image_stays_in_the_output_of_its_call(
        self, is_error: bool, prefix: list[dict[str, object]]
    ) -> None:
        request = convert(
            user(
                [
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_1",
                        "is_error": is_error,
                        "content": [
                            {"type": "text", "text": "Screenshot"},
                            {
                                "type": "image",
                                "source": {"type": "url", "url": "https://x"},
                            },
                            {"type": "tool_reference", "tool_name": "search"},
                        ],
                    }
                ]
            )
        )
        assert request["input"] == [
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": [
                    *prefix,
                    {"type": "input_text", "text": "Screenshot"},
                    {
                        "type": "input_image",
                        "image_url": "https://x",
                        "detail": "auto",
                    },
                ],
            }
        ]


class TestAssistantTurn:
    def test_string_content(self) -> None:
        request = convert(
            {"messages": [{"role": "assistant", "content": "Hi"}]}
        )
        assert request["input"] == [
            {"type": "message", "role": "assistant", "content": "Hi"}
        ]

    def test_blocks_keep_their_order(self) -> None:
        request = convert(
            {
                "messages": [
                    {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "thinking",
                                "thinking": "Hmm",
                                "signature": signature(),
                            },
                            {"type": "text", "text": "Let me"},
                            {"type": "text", "text": "check"},
                            {
                                "type": "tool_use",
                                "id": "call_1",
                                "name": "search",
                                "input": {"q": "x"},
                            },
                            {"type": "text", "text": "Done"},
                        ],
                    }
                ]
            }
        )
        assert request["input"] == [
            {
                "type": "reasoning",
                "id": "rs_1",
                "encrypted_content": "ENC",
                "summary": [{"type": "summary_text", "text": "Hmm"}],
            },
            {
                "type": "message",
                "role": "assistant",
                "content": "Let me\ncheck",
            },
            {
                "type": "function_call",
                "call_id": "call_1",
                "name": "search",
                "arguments": '{"q": "x"}',
            },
            {"type": "message", "role": "assistant", "content": "Done"},
        ]

    def test_redacted_thinking_is_replayed_without_a_summary(self) -> None:
        request = convert(
            {
                "messages": [
                    {
                        "role": "assistant",
                        "content": [
                            {"type": "redacted_thinking", "data": signature()}
                        ],
                    }
                ]
            }
        )
        assert request["input"] == [
            {
                "type": "reasoning",
                "id": "rs_1",
                "encrypted_content": "ENC",
                "summary": [],
            }
        ]

    @pytest.mark.parametrize(
        "block",
        [
            {"type": "thinking", "thinking": "Hmm", "signature": "EqQBCgIYAh"},
            {"type": "thinking", "thinking": "Hmm", "signature": ""},
            {"type": "redacted_thinking", "data": "EmwKAhgB"},
            {
                "type": "thinking",
                "thinking": "Hmm",
                "signature": '{"dial_translator_reasoning_wrapper":{"version":1}}',
            },
        ],
        ids=["claude", "unsigned", "claude-redacted", "other-version"],
    )
    def test_foreign_thinking_is_dropped(self, block: dict[str, str]) -> None:
        request = convert(
            {"messages": [{"role": "assistant", "content": [block]}]}
        )
        assert request["input"] == []

    def test_tool_use_without_input_sends_an_empty_object(self) -> None:
        request = convert(
            {
                "messages": [
                    {
                        "role": "assistant",
                        "content": [
                            {"type": "tool_use", "id": "call_1", "name": "now"}
                        ],
                    }
                ]
            }
        )
        assert request["input"][0]["arguments"] == "{}"


class TestTools:
    def test_custom_tool_becomes_a_function(self) -> None:
        request = convert(
            {
                "tools": [
                    {
                        "name": "search",
                        "description": "Searches",
                        "input_schema": {
                            "$schema": "https://json-schema.org/draft/2020-12/schema",
                            "type": "object",
                        },
                    },
                    {"type": "custom", "name": "now", "strict": True},
                ],
                **user("Hi"),
            }
        )
        assert request["tools"] == [
            {
                "type": "function",
                "name": "search",
                "description": "Searches",
                "parameters": {"type": "object"},
                "strict": False,
            },
            {
                "type": "function",
                "name": "now",
                "parameters": {"type": "object", "properties": {}},
                "strict": True,
            },
        ]

    def test_web_search_becomes_the_built_in_tool(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            request = convert(
                {
                    "tools": [
                        {
                            "type": "web_search_20250305",
                            "name": "web_search",
                            "max_uses": 3,
                            "allowed_domains": ["example.com"],
                            "blocked_domains": ["bad.com"],
                            "user_location": {
                                "type": "approximate",
                                "city": "Paris",
                            },
                        }
                    ],
                    **user("Hi"),
                }
            )
        assert request["tools"] == [
            {
                "type": "web_search",
                "filters": {"allowed_domains": ["example.com"]},
                "user_location": {
                    "type": "approximate",
                    "city": "Paris",
                    "country": None,
                    "region": None,
                    "timezone": None,
                },
            }
        ]
        assert request["max_tool_calls"] == 3
        assert caplog.messages == [
            "Dropping web_search blocked_domains: "
            "no Responses API equivalent, the search isn't restricted"
        ]

    def test_max_uses_of_several_web_searches_is_dropped(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        search = {"type": "web_search_20250305", "name": "web_search"}
        with caplog.at_level(logging.WARNING):
            request = convert(
                {"tools": [{**search, "max_uses": 3}, search], **user("Hi")}
            )
        assert "max_tool_calls" not in request
        assert caplog.messages == [
            "Dropping web_search max_uses: several web search tools "
            "can't share one Responses API max_tool_calls"
        ]

    def test_tool_without_counterpart_is_forwarded_as_sent(self) -> None:
        tool = {"type": "bash_20250124", "name": "bash"}
        assert convert({"tools": [tool], **user("Hi")})["tools"] == [tool]

    def test_long_names_are_aliased_everywhere(self) -> None:
        translation_state = TranslationState()
        request = convert(
            {
                "tools": [{"name": LONG_MCP_NAME, "input_schema": {}}],
                "tool_choice": {"type": "tool", "name": LONG_MCP_NAME},
                "messages": [
                    {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "call_1",
                                "name": LONG_MCP_NAME,
                                "input": {},
                            }
                        ],
                    }
                ],
            },
            translation_state,
        )
        assert request["tools"][0]["name"] == LONG_MCP_ALIAS
        assert request["tool_choice"] == {
            "type": "function",
            "name": LONG_MCP_ALIAS,
        }
        assert request["input"][0]["name"] == LONG_MCP_ALIAS
        assert translation_state.to_client_tool_name(LONG_MCP_ALIAS) == (
            LONG_MCP_NAME
        )


class TestToolChoice:
    @pytest.mark.parametrize(
        "tool_choice, expected",
        [
            ({"type": "auto"}, "auto"),
            ({"type": "any"}, "required"),
            ({"type": "none"}, "none"),
            (
                {"type": "tool", "name": "search"},
                {"type": "function", "name": "search"},
            ),
        ],
        ids=["auto", "any", "none", "tool"],
    )
    def test_type(self, tool_choice: dict[str, str], expected: object) -> None:
        request = convert({"tool_choice": tool_choice, **user("Hi")})
        assert request["tool_choice"] == expected

    def test_forcing_web_search_requires_the_built_in_tool(self) -> None:
        request = convert(
            {
                "tools": [
                    {"type": "web_search_20250305", "name": "web_search"}
                ],
                "tool_choice": {"type": "tool", "name": "web_search"},
                **user("Hi"),
            }
        )
        assert request["tool_choice"] == {
            "type": "allowed_tools",
            "mode": "required",
            "tools": [{"type": "web_search"}],
        }

    @pytest.mark.parametrize(
        "disable, parallel", [(True, False), (False, True)], ids=["off", "on"]
    )
    def test_parallel_tool_calls(self, disable: bool, parallel: bool) -> None:
        request = convert(
            {
                "tool_choice": {
                    "type": "auto",
                    "disable_parallel_tool_use": disable,
                },
                **user("Hi"),
            }
        )
        assert request["parallel_tool_calls"] is parallel


class TestReasoning:
    @pytest.mark.parametrize(
        "params, reasoning",
        [
            ({"thinking": {"type": "adaptive"}}, {"summary": "auto"}),
            (
                {
                    "thinking": {"type": "enabled", "budget_tokens": 1024},
                    "output_config": {"effort": "high"},
                },
                {"effort": "high", "summary": "auto"},
            ),
            ({"output_config": {"effort": "max"}}, {"effort": "max"}),
            (
                {"thinking": {"type": "adaptive", "display": "omitted"}},
                None,
            ),
            (
                {
                    "thinking": {"type": "disabled"},
                    "output_config": {"effort": "high"},
                },
                {"effort": "none"},
            ),
            ({}, None),
        ],
        ids=[
            "adaptive",
            "effort-and-thinking",
            "effort-only",
            "omitted-display",
            "disabled",
            "absent",
        ],
    )
    def test_reasoning(
        self, params: dict[str, object], reasoning: dict[str, str] | None
    ) -> None:
        assert convert({**params, **user("Hi")}).get("reasoning") == reasoning

    def test_per_turn_effort_outranks_the_request_effort(self) -> None:
        request = convert(
            {
                "output_config": {"effort": "low"},
                "messages": [
                    {"role": "user", "content": "Hi"},
                    {
                        "role": "system",
                        "content": "Think hard",
                        "output_config": {"effort": "high"},
                    },
                ],
            }
        )
        assert request["reasoning"] == {"effort": "high"}

    def test_unknown_effort_is_rejected(self) -> None:
        with pytest.raises(InvalidRequestError) as e:
            convert({"output_config": {"effort": "extreme"}, **user("Hi")})
        assert e.value.message == (
            "Cannot convert Anthropic Messages API reasoning effort extreme "
            "to an OpenAI reasoning effort"
        )


class TestOutputFormat:
    def test_json_schema_becomes_text_format(self) -> None:
        request = convert(
            {
                "output_config": {
                    "format": {
                        "type": "json_schema",
                        "schema": {"type": "object"},
                    }
                },
                **user("Hi"),
            }
        )
        assert request["text"] == {
            "format": {
                "type": "json_schema",
                "name": "response",
                "schema": {"type": "object"},
                "strict": True,
            }
        }

    @pytest.mark.parametrize(
        "output_format, warning",
        [
            (
                {"type": "xml"},
                "Dropping unsupported output_config.format type: xml",
            ),
            (
                {"type": "json_schema"},
                "Dropping output_config.format: missing 'schema'",
            ),
        ],
        ids=["unsupported-type", "missing-schema"],
    )
    def test_untranslatable_format_is_dropped(
        self,
        output_format: dict[str, str],
        warning: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with caplog.at_level(logging.WARNING):
            request = convert(
                {"output_config": {"format": output_format}, **user("Hi")}
            )
        assert "text" not in request
        assert caplog.messages == [warning]


@pytest.mark.parametrize(
    "user_id, expected",
    [("user-1", "user-1"), ("x" * 65, None), ("", None)],
    ids=["fits", "too-long", "empty"],
)
def test_user(user_id: str, expected: str | None) -> None:
    request = convert({"metadata": {"user_id": user_id}, **user("Hi")})
    assert request.get("user") == expected


@pytest.mark.parametrize(
    "service_tier, expected",
    [("auto", "auto"), ("standard_only", "default"), ("priority", None)],
    ids=["auto", "standard-only", "unknown"],
)
def test_service_tier(service_tier: str, expected: str | None) -> None:
    request = convert({"service_tier": service_tier, **user("Hi")})
    assert request.get("service_tier") == expected


def test_sampling_parameters_are_passed_through() -> None:
    request = convert({"temperature": 0.5, "top_p": 0.9, **user("Hi")})
    assert (request["temperature"], request["top_p"]) == (0.5, 0.9)


def test_parameters_without_counterpart_are_dropped_with_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        request = convert(
            {
                "top_k": 5,
                "stop_sequences": ["END"],
                "cache_control": {"type": "ephemeral"},
                **user("Hi"),
            }
        )
    assert set(request) == {"model", "input", "store", "include", "stream"}
    assert caplog.messages == [
        "Ignoring Anthropic Messages API parameters that have no "
        "Responses API equivalent: top_k, stop_sequences."
    ]
