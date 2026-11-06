import json
from collections.abc import Mapping
from typing import Any, cast

from anthropic.types.beta.message_create_params import MessageCreateParams

from aidial_sdk.translators.messages_to_chat_completions.translation_state import (
    TranslationState,
)
from aidial_sdk.translators.messages_to_responses.to_responses import (
    to_responses_request,
)

MODEL = "gpt-5.5"

LONG_MCP_NAME = "mcp__" + "s" * 60 + "__do_the_thing"
LONG_MCP_ALIAS = TranslationState().to_upstream_tool_name(LONG_MCP_NAME)


def convert(
    body: Mapping[str, object],
    translation_state: TranslationState | None = None,
) -> dict[str, Any]:
    """The Responses request body the handler gets."""
    request = to_responses_request(
        cast(MessageCreateParams, {"model": MODEL, **body}),
        translation_state or TranslationState(),
    )
    return json.loads(json.dumps(request))


def user(content: str | list[dict[str, object]]) -> dict[str, object]:
    return {"messages": [{"role": "user", "content": content}]}


def signature(id: str = "rs_1", encrypted_content: str = "ENC") -> str:
    return json.dumps(
        {
            "dial_translator_reasoning_wrapper": {
                "version": 2,
                "id": id,
                "encrypted_content": encrypted_content,
            }
        },
        separators=(",", ":"),
    )


def responses_body(
    output: list[dict[str, object]], **fields: Any
) -> dict[str, Any]:
    return {
        "id": "resp_1",
        "object": "response",
        "created_at": 0,
        "model": "gpt-5.5-2026-01-01",
        "status": "completed",
        "output": output,
        "usage": None,
        **fields,
    }


def text_item(text: str, annotations: list[dict[str, object]] | None = None):
    return {
        "type": "message",
        "id": "msg_1",
        "role": "assistant",
        "status": "completed",
        "content": [
            {
                "type": "output_text",
                "text": text,
                "annotations": annotations or [],
            }
        ],
    }


def reasoning_item(
    summary: list[str], encrypted_content: str | None = "ENC"
) -> dict[str, object]:
    return {
        "type": "reasoning",
        "id": "rs_1",
        "summary": [{"type": "summary_text", "text": text} for text in summary],
        "encrypted_content": encrypted_content,
    }


def function_call_item(
    name: str = "search", arguments: str = '{"q": "x"}'
) -> dict[str, object]:
    return {
        "type": "function_call",
        "id": "fc_1",
        "call_id": "call_1",
        "name": name,
        "arguments": arguments,
        "status": "completed",
    }


def url_citation(url: str, title: str = "Title") -> dict[str, object]:
    return {
        "type": "url_citation",
        "url": url,
        "title": title,
        "start_index": 0,
        "end_index": 1,
    }
