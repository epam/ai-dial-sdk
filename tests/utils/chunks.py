import itertools
import json
from typing import Iterable, List, Literal, Optional, Union

from aidial_sdk.utils.json import remove_nones


def create_chunk(
    *,
    id: str = "test_id",
    model: Optional[str] = None,
    created: int = 0,
    choices: List[dict],
    usage: Optional[dict] = None,
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
    finish_reason: Optional[str] = None,
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
    type: Optional[Literal["function"]] = None,
    id: Optional[str] = None,
    name: Optional[str] = None,
    arguments: Optional[str] = None,
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
    name: Optional[str] = None,
    arguments: Optional[str] = None,
):
    return create_single_choice_chunk(
        delta={
            "content": None,
            "function_call": remove_nones(
                {"name": name, "arguments": arguments}
            ),
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
