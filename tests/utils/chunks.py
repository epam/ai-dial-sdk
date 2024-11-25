import itertools
import json
from typing import List, Literal, Optional, Union


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


def create_single_choice_chunk(
    delta: dict = {}, finish_reason: Optional[str] = None, **kwargs
):
    return {
        "choices": [
            {
                "index": 0,
                "finish_reason": finish_reason,
                "delta": delta,
            }
        ],
        "usage": None,
        "id": "test_id",
        "created": 0,
        "object": "chat.completion.chunk",
        **kwargs,
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


def _check_chunk(actual: str, expected: Union[str, dict]):
    assert actual.startswith("data: "), f"Invalid data SSE entry: {actual!r}"
    actual = actual[len("data: ") :]

    if isinstance(expected, str):
        assert (
            actual == expected
        ), f"actual != expected: {actual!r} != {expected!r}"
    else:
        try:
            actual_dict = json.loads(actual)
        except json.JSONDecodeError:
            raise AssertionError(f"Invalid JSON in data SSE entry: {actual!r}")
        assert (
            actual_dict == expected
        ), f"actual != expected: {actual_dict!r} != {expected!r}"


def check_sse_stream(actual: List[str], expected: List[dict]):
    for e_chunk in itertools.chain(expected, ["[DONE]"]):
        a_chunk = actual.pop(0)
        _check_chunk(a_chunk, e_chunk)
        a_chunk = actual.pop(0)
        assert a_chunk == ""

    assert actual == [], f"There are more SSE entries than expected: {actual!r}"
