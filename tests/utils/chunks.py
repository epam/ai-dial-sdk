import itertools
import json
from typing import Iterable, Literal, Optional, Union

from aidial_sdk.utils.json import remove_nones


def create_chunk(
    *,
    choice_idx: int = 0,
    delta: dict = {},
    finish_reason: Optional[str] = None,
    **kwargs,
):
    return {
        "id": "test_id",
        "object": "chat.completion.chunk",
        "created": 0,
        "choices": [
            {
                "index": choice_idx,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
        "usage": None,
        **kwargs,
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
            "content": None,
            "tool_calls": [
                remove_nones(
                    {
                        "index": idx,
                        "id": id,
                        "type": type,
                        "function": remove_nones(
                            {"name": name, "arguments": arguments}
                        ),
                    }
                )
            ],
        }
    )


def _check_sse_line(actual: str, expected: Union[str, dict]):
    if isinstance(expected, str):
        assert actual == expected
        return

    assert actual.startswith("data: "), f"Invalid data SSE entry: {actual!r}"
    actual = actual[len("data: ") :]

    try:
        actual_dict = json.loads(actual)
    except json.JSONDecodeError:
        raise AssertionError(f"Invalid JSON in data SSE entry: {actual!r}")

    assert actual_dict == expected


ExpectedSSEStream = Iterable[Union[str, dict]]


def check_sse_stream(
    actual: Iterable[str], expected: ExpectedSSEStream
) -> bool:
    expected = itertools.chain(expected, ["data: [DONE]"])
    expected = itertools.chain.from_iterable((line, "") for line in expected)

    sentinel = object()
    for a_line, e_obj in itertools.zip_longest(
        actual, expected, fillvalue=sentinel
    ):
        assert (
            a_line is not sentinel
        ), "The list of actual values is shorter than the list of expected values"
        assert (
            e_obj is not sentinel
        ), "The list of expected values is shorter than the list of actual values"

        _check_sse_line(a_line, e_obj)  # type: ignore

    return True
