import itertools
import json
from collections.abc import Iterable
from typing import Literal

from aidial_sdk.utils.json import remove_nones


def create_chunk(
    *,
    id: str = "test_id",
    model: str | None = None,
    created: int = 0,
    choices: list[dict],
    usage: dict | None = None,
    **kwargs,
):
    return {
        "id": id,
        **({} if model is None else {"model": model}),
        "created": created,
        "object": "chat.completion.chunk",
        "choices": choices,
        "usage": usage,
        **kwargs,
    }


def create_single_choice_chunk(
    *,
    choice_idx: int = 0,
    delta: dict = {},
    finish_reason: str | None = None,
    **kwargs,
):
    choice = {
        "index": choice_idx,
        "delta": delta,
        "finish_reason": finish_reason,
    }

    return create_chunk(choices=[choice], **kwargs)


def create_tool_call_chunk(
    idx: int,
    *,
    type: Literal["function"] | None = None,
    id: str | None = None,
    name: str | None = None,
    arguments: str | None = None,
):
    return create_single_choice_chunk(
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


def create_function_call_chunk(
    *,
    name: str | None = None,
    arguments: str | None = None,
):
    return create_single_choice_chunk(
        delta={
            "content": None,
            "function_call": remove_nones(
                {"name": name, "arguments": arguments}
            ),
        }
    )


def _check_sse_line(actual: str, expected: str | dict):
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


ExpectedSSEStream = Iterable[str | dict]


def check_sse_stream(
    actual: Iterable[str], expected: ExpectedSSEStream
) -> bool:
    expected = itertools.chain(expected, ["data: [DONE]"])
    expected = itertools.chain.from_iterable((line, "") for line in expected)

    sentinel = object()
    for a_line, e_obj in itertools.zip_longest(
        actual, expected, fillvalue=sentinel
    ):
        assert a_line is not sentinel, (
            "The list of actual values is shorter than the list of expected values"
        )
        assert e_obj is not sentinel, (
            "The list of expected values is shorter than the list of actual values"
        )

        _check_sse_line(a_line, e_obj)  # type: ignore

    return True
