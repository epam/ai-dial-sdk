from typing import Literal, Optional


def create_chunk(
    *,
    choice_idx: int = 0,
    delta: dict = {},
    finish_reason: Optional[str] = None,
):
    return {
        "id": "chatcmpl-AQws8iVykPBIQJfnmCQnMEkTLLUUA",
        "object": "chat.completion.chunk",
        "created": 1730986196,
        "model": "gpt-4o-2024-05-13",
        "system_fingerprint": "fp_67802d9a6d",
        "choices": [
            {
                "index": choice_idx,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }


def create_tool_call_chunk(
    idx: int,
    *,
    type: Optional[Literal["function"]] = None,
    id: Optional[str] = None,
    name: Optional[str] = None,
    arguments: Optional[str] = None,
):
    return create_chunk(
        delta={
            "tool_calls": [
                {
                    "index": idx,
                    "id": id,
                    "type": type,
                    "function": {"name": name, "arguments": arguments},
                }
            ]
        }
    )
