from typing import Optional


def create_chunk(
    *,
    choice_idx: int = 0,
    delta: dict = {},
    finish_reason: Optional[str] = None
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
