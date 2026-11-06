from typing import Any
from unittest.mock import ANY

import pytest
from openai.types.responses import Response

from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.translators._messages.translation_state import (
    TranslationState,
)
from aidial_sdk.translators.messages_to_responses.from_responses import (
    to_anthropic_message,
)
from tests.translators.messages_to_responses.helpers import (
    LONG_MCP_ALIAS,
    LONG_MCP_NAME,
    function_call_item,
    reasoning_item,
    responses_body,
    signature,
    text_item,
    url_citation,
)


def translate(
    output: list[dict[str, object]],
    translation_state: TranslationState | None = None,
    **fields: Any,
) -> dict[str, Any]:
    response = Response.model_construct(**responses_body(output, **fields))
    message = to_anthropic_message(
        response, "gpt-5.5", translation_state or TranslationState()
    )
    return message.model_dump(mode="json", exclude_unset=True)


def test_text() -> None:
    assert translate(
        [text_item("Hello")],
        usage={
            "input_tokens": 10,
            "input_tokens_details": {"cached_tokens": 4},
            "output_tokens": 5,
            "output_tokens_details": {"reasoning_tokens": 2},
            "total_tokens": 15,
        },
    ) == {
        "id": "resp_1",
        "type": "message",
        "role": "assistant",
        "model": "gpt-5.5",
        "content": [{"type": "text", "text": "Hello"}],
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": 6,
            "output_tokens": 5,
            "cache_read_input_tokens": 4,
            "cache_creation_input_tokens": 0,
            "output_tokens_details": {"thinking_tokens": 2},
            "server_tool_use": None,
        },
    }


def test_empty_output_gets_an_empty_text_block() -> None:
    assert translate([])["content"] == [{"type": "text", "text": ""}]


def test_unknown_output_item_is_dropped() -> None:
    message = translate([{"type": "teleport_call", "id": "tp_1"}])
    assert message["content"] == [{"type": "text", "text": ""}]


class TestReasoning:
    def test_encrypted_reasoning_with_text_is_signed_thinking(self) -> None:
        message = translate([reasoning_item(["One", "Two"])])
        assert message["content"] == [
            {
                "type": "thinking",
                "thinking": "One\n\nTwo",
                "signature": signature(),
            }
        ]

    def test_encrypted_reasoning_without_text_is_redacted_thinking(
        self,
    ) -> None:
        message = translate([reasoning_item([])])
        assert message["content"] == [
            {"type": "redacted_thinking", "data": signature()}
        ]

    def test_unencrypted_reasoning_is_unsigned_thinking(self) -> None:
        message = translate([reasoning_item(["One"], encrypted_content=None)])
        assert message["content"] == [
            {"type": "thinking", "thinking": "One", "signature": ""}
        ]

    def test_unencrypted_reasoning_without_text_is_dropped(self) -> None:
        message = translate(
            [reasoning_item([], encrypted_content=None), text_item("Hi")]
        )
        assert message["content"] == [{"type": "text", "text": "Hi"}]


class TestFunctionCall:
    def test_becomes_tool_use(self) -> None:
        message = translate([function_call_item()])
        assert message["content"] == [
            {
                "type": "tool_use",
                "id": "call_1",
                "name": "search",
                "input": {"q": "x"},
            }
        ]
        assert message["stop_reason"] == "tool_use"

    def test_restores_the_aliased_name(self) -> None:
        translation_state = TranslationState()
        translation_state.to_upstream_tool_name(LONG_MCP_NAME)
        message = translate(
            [function_call_item(name=LONG_MCP_ALIAS)], translation_state
        )
        assert message["content"][0]["name"] == LONG_MCP_NAME

    @pytest.mark.parametrize(
        "arguments", ["{not json", "[1, 2]"], ids=["invalid", "not-object"]
    )
    def test_unparsable_arguments_become_an_empty_input(
        self, arguments: str
    ) -> None:
        message = translate([function_call_item(arguments=arguments)])
        assert message["content"][0]["input"] == {}


def test_refusal() -> None:
    message = translate(
        [
            {
                "type": "message",
                "id": "msg_1",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "refusal", "refusal": "I can't"}],
            }
        ]
    )
    assert message["content"] == [{"type": "text", "text": "I can't"}]
    assert message["stop_reason"] == "refusal"


@pytest.mark.parametrize(
    "reason, stop_reason",
    [("max_output_tokens", "max_tokens"), ("content_filter", "refusal")],
    ids=["max-output-tokens", "content-filter"],
)
def test_incomplete_response_outranks_a_tool_call(
    reason: str, stop_reason: str
) -> None:
    message = translate(
        [function_call_item()],
        status="incomplete",
        incomplete_details={"reason": reason},
    )
    assert message["stop_reason"] == stop_reason


def test_citations_follow_the_text_that_cites_them() -> None:
    message = translate(
        [
            text_item(
                "A", [url_citation("https://a"), url_citation("https://b")]
            ),
            text_item("B", [url_citation("https://a")]),
        ]
    )
    assert message["content"] == [
        {"type": "text", "text": "A"},
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
                },
                {
                    "type": "web_search_result",
                    "url": "https://b",
                    "title": "Title",
                    "encrypted_content": "",
                },
            ],
        },
        {"type": "text", "text": "B"},
    ]


class TestUsage:
    def test_cache_breakdown_is_capped_by_the_input_tokens(self) -> None:
        message = translate(
            [text_item("Hi")],
            usage={
                "input_tokens": 10,
                "input_tokens_details": {
                    "cached_tokens": 8,
                    "cache_write_tokens": 5,
                },
                "output_tokens": 1,
                "output_tokens_details": {"reasoning_tokens": 0},
                "total_tokens": 11,
            },
        )
        assert message["usage"] == {
            "input_tokens": 0,
            "output_tokens": 1,
            "cache_read_input_tokens": 8,
            "cache_creation_input_tokens": 2,
            "output_tokens_details": {"thinking_tokens": 0},
            "server_tool_use": None,
        }

    def test_web_search_calls_are_counted(self) -> None:
        def web_search(action: str) -> dict[str, object]:
            return {
                "type": "web_search_call",
                "id": "ws_1",
                "status": "completed",
                "action": {"type": action},
            }

        message = translate(
            [
                web_search("search"),
                web_search("search"),
                web_search("open_page"),
            ]
        )
        assert message["usage"] == {
            "input_tokens": 0,
            "output_tokens": 0,
            "server_tool_use": {
                "web_search_requests": 2,
                "web_fetch_requests": 1,
            },
        }


@pytest.mark.parametrize(
    "code, status_code",
    [
        ("rate_limit_exceeded", 429),
        ("server_error", 500),
        ("invalid_prompt", 400),
        ("image_too_large", 400),
        ("brand_new_code", 500),
    ],
    ids=["rate-limit", "server-error", "invalid-prompt", "image", "unknown"],
)
def test_failed_response_is_an_error(code: str, status_code: int) -> None:
    with pytest.raises(DIALException) as e:
        translate(
            [], status="failed", error={"code": code, "message": "It failed"}
        )
    assert (e.value.message, e.value.status_code) == ("It failed", status_code)


def test_failed_response_without_an_error_is_an_internal_error() -> None:
    with pytest.raises(DIALException) as e:
        translate([], status="failed")
    assert (e.value.message, e.value.status_code) == (
        "The Responses API response has failed",
        500,
    )
