import copy
import itertools
import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from operator import attrgetter
from typing import Any

import pytest

from aidial_sdk.utils._indexed_list import (
    INCONSISTENT_INDEXED_LIST_ERROR_MESSAGE,
    INDEX_INTEGER_ERROR_MESSAGE,
    INDEX_NON_NEGATIVE_ERROR_MESSAGE,
)
from aidial_sdk.utils.merge_chunks import (
    CANNOT_MERGE_NON_INDEXED_AND_INDEXED_LISTS_ERROR_MESSAGE,
    cleanup_indices,
    merge,
    merge_chat_completion_chunks,
)
from tests.utils.chunks import (
    create_chunk,
    create_single_choice_chunk,
    create_tool_call_chunk,
)
from tests.utils.sharing import collect_shared_mutable_objects


class OrderConstraint(ABC):
    @abstractmethod
    def satisfy(self, orig_seq: Sequence[Any], seq: Sequence[Any]) -> bool:
        pass


@dataclass
class Fixed(OrderConstraint):
    idx: int

    def satisfy(self, orig_seq: Sequence[Any], seq: Sequence[Any]) -> bool:
        return orig_seq[self.idx] == seq[self.idx]


@dataclass
class BeforeValue(OrderConstraint):
    elem1: Any
    elem2: Any

    def satisfy(self, orig_seq: Sequence[Any], seq: Sequence[Any]) -> bool:
        # NOTE: it only works when elem1 and elem2 are unique elements in the sequence
        return seq.index(self.elem1) < seq.index(self.elem2)


@dataclass
class BeforeIdx(OrderConstraint):
    idx1: int
    idx2: int

    def satisfy(self, orig_seq: Sequence[Any], seq: Sequence[Any]) -> bool:
        return BeforeValue(orig_seq[self.idx1], orig_seq[self.idx2]).satisfy(
            orig_seq, seq
        )


class Test:
    __test__ = False  # Hide from pytest test discovery

    chunks: list[Any]
    expected: Any | Exception
    desc: str

    fixed_order: bool
    order_constraints: list[OrderConstraint]

    def __init__(
        self,
        chunks: list[Any],
        expected: Any,
        desc: str,
        fixed_order: bool = False,
        order_constraints: list[OrderConstraint] = [],
    ):
        self.chunks = copy.deepcopy(chunks)
        self.expected = expected
        self.desc = desc.replace(" ", "_").lower()
        self.fixed_order = fixed_order
        self.order_constraints = order_constraints

    def permutations(self) -> Iterable["Test"]:
        if self.fixed_order:
            yield self
            return

        n = len(self.chunks)
        for indices in itertools.permutations(range(n)):
            chunks = [self.chunks[idx] for idx in indices]
            if all(
                c.satisfy(self.chunks, chunks) for c in self.order_constraints
            ):
                yield Test(
                    chunks=list(chunks),
                    expected=self.expected,
                    desc=f"{self.desc} {' '.join(map(str, indices))}",
                )


def permute(cases: list[Test]) -> Iterable[Test]:
    for case in cases:
        yield from case.permutations()


merge_chunks_cases: list[Test] = [
    Test(chunks=[1, 2], expected=2, desc="Merge ints", fixed_order=True),
    Test(
        chunks=[1.0, 2.0], expected=2.0, desc="Merge floats", fixed_order=True
    ),
    Test(
        chunks=["foo", "bar"],
        expected="foobar",
        desc="Merge strings",
        fixed_order=True,
    ),
    Test(
        chunks=[True, False],
        expected=False,
        desc="Merge bools",
        fixed_order=True,
    ),
    Test(chunks=[{}], expected={}, desc="Merge empty dicts"),
    Test(chunks=[1, None], expected=1, desc="Merge with None right"),
    Test(chunks=[None, 1], expected=1, desc="Merge with None left"),
    Test(chunks=[None, []], expected=[], desc="Merge with None left list"),
    Test(chunks=[[], None], expected=[], desc="Merge with None right list"),
    Test(chunks=[None, {}], expected={}, desc="Merge with None left dict"),
    Test(chunks=[{}, None], expected={}, desc="Merge with None right dict"),
    Test(
        chunks=[{"a": {"b": "foo"}}, {"a": {"b": 1}}],
        expected=TypeError(
            "Cannot merge 'str' with incoming 'int' at path $.a.b"
        ),
        fixed_order=True,
        desc="str+int type-error",
    ),
    Test(
        chunks=[{"a": ("foo", "bar")}, {"a": ("baz", "quz")}],
        expected=TypeError(
            "Cannot merge 'tuple' with incoming 'tuple' at path $.a"
        ),
        fixed_order=True,
        desc="tuple+tuple type-error",
    ),
    Test(
        chunks=[{"a": {"b": 1}}, {"a": {"b": "foo"}}],
        expected=TypeError(
            "Cannot merge 'int' with incoming 'str' at path $.a.b"
        ),
        fixed_order=True,
        desc="int+str type-error",
    ),
    Test(
        chunks=[{}, {"a": {"b": 1}}],
        expected={"a": {"b": 1}},
        desc="Merge to empty dict",
    ),
    Test(
        chunks=[{}, {"a": []}],
        expected={"a": []},
        desc="Merge to empty dict with empty list",
    ),
    Test(
        chunks=[{}, {"a": [1]}],
        expected={"a": [1]},
        desc="Merge to empty dict with non-empty non-indexed list",
    ),
    Test(
        chunks=[{}, {"a": [{"index": 0}, {"value": 1}]}],
        expected=AssertionError(INCONSISTENT_INDEXED_LIST_ERROR_MESSAGE),
        desc="Inconsistent list indexing #1",
    ),
    Test(
        chunks=[{"a": [{"index": 0}, {"value": 1}]}],
        expected=AssertionError(INCONSISTENT_INDEXED_LIST_ERROR_MESSAGE),
        desc="Inconsistent list indexing #2",
    ),
    Test(
        chunks=[{"a": [2]}, {"a": [{"index": 0}]}],
        expected=AssertionError(
            CANNOT_MERGE_NON_INDEXED_AND_INDEXED_LISTS_ERROR_MESSAGE
        ),
        desc="Merge non-indexed and indexed lists",
    ),
    Test(
        chunks=[{"a": [{"index": 0}]}, {"a": [2]}],
        expected=AssertionError(
            CANNOT_MERGE_NON_INDEXED_AND_INDEXED_LISTS_ERROR_MESSAGE
        ),
        desc="Merge indexed and non-indexed lists",
    ),
    Test(
        chunks=[{"a": [{"index": -1}]}],
        expected=AssertionError(
            INDEX_NON_NEGATIVE_ERROR_MESSAGE.format(index=-1)
        ),
        desc="Negative index in a list element",
    ),
    Test(
        chunks=[{"a": [{"index": "a"}]}],
        expected=AssertionError(INDEX_INTEGER_ERROR_MESSAGE.format(ty="str")),
        desc="Non-integer index in a list element",
    ),
    Test(
        chunks=[{"a": [1]}, {"a": [2]}],
        expected={"a": [1, 2]},
        fixed_order=True,
        desc="Merge lists of non-dicts",
    ),
    Test(
        chunks=[{"a": [{"b": 1}]}, {"a": [{"c": 2}]}],
        expected={"a": [{"b": 1}, {"c": 2}]},
        fixed_order=True,
        desc="Merge lists of non-indexed dicts",
    ),
    Test(
        chunks=[{"a": 1, "b": 2}, {"c": 3, "d": 4}],
        expected={"a": 1, "b": 2, "c": 3, "d": 4},
        desc="Merge dicts with non-overlapping keys",
    ),
    Test(
        chunks=[{"a": 1, "b": 2}, {"c": 3, "b": 4}],
        expected={"a": 1, "b": 4, "c": 3},
        desc="Merge dicts with overlapping keys",
        fixed_order=True,
    ),
    Test(
        chunks=[
            {"a": [{"index": 0, "value": 1}]},
            {"a": [{"index": 0, "value": 2}]},
        ],
        expected={"a": [{"value": 2}]},
        fixed_order=True,
        desc="Merge lists with overlapping indices",
    ),
    Test(
        chunks=[
            {"a": [{"index": 0, "value": 0}]},
            {"a": [{"index": 1, "value": 1}]},
        ],
        expected={"a": [{"value": 0}, {"value": 1}]},
        desc="Merge lists with non-overlapping indices",
    ),
    Test(
        chunks=[
            {"a": []},
            {"a": [{"index": 1, "value": 1}]},
            {"a": [{"index": 0, "value": 0}]},
        ],
        expected={"a": [{"value": 0}, {"value": 1}]},
        desc="Merge lists out-of-order",
    ),
    Test(
        chunks=[
            {"a": [{"index": 5, "value": 5}]},
            {"a": [{"index": 4, "value": 4}]},
            {"a": [{"index": 2, "value": 2}]},
            {"a": [{"index": 1, "value": 1}]},
        ],
        expected={
            "a": [
                {},
                {"value": 1},
                {"value": 2},
                {},
                {"value": 4},
                {"value": 5},
            ]
        },
        desc="Merge lists out-of-order (no starting point)",
    ),
    Test(
        chunks=[
            {"a": [{"index": 0, "value": 0}]},
            {"a": [{"index": 2, "value": 2}]},
        ],
        expected={"a": [{"value": 0}, {}, {"value": 2}]},
        desc="Merge lists with a forward gap",
    ),
    Test(
        chunks=[
            {"a": [{"index": 2, "value": 2}, {"index": 1, "value": 1}]},
            {"a": [{"index": 3, "value": 3}, {"index": 0, "value": 0}]},
        ],
        expected={
            "a": [{"value": 0}, {"value": 1}, {"value": 2}, {"value": 3}]
        },
        desc="Merge indexed lists. First list: with gaps and out-of-order",
    ),
    Test(
        chunks=[
            {"a": [{"index": 1, "value": 1}, {"index": 0, "value": 0}]},
            {"a": [{"index": 3, "value": 3}, {"index": 2, "value": 2}]},
        ],
        expected={
            "a": [{"value": 0}, {"value": 1}, {"value": 2}, {"value": 3}]
        },
        desc="Merge indexed lists. First list: no gaps and out-of-order",
    ),
    Test(
        chunks=[
            {"a": [{"index": 1, "value": 1}, {"index": 0, "value": 0}]},
        ],
        expected={"a": [{"value": 0}, {"value": 1}]},
        desc="Remove indices from indexed out-of-order list without gaps",
    ),
    Test(
        chunks=[
            {"a": [{"index": 2, "value": 2}, {"index": 0, "value": 0}]},
        ],
        expected={"a": [{"value": 0}, {}, {"value": 2}]},
        desc="Remove indices from indexed out-of-order list with gaps",
    ),
    Test(
        chunks=[{"a": "Hello "}, {"a": "world!"}],
        expected={"a": "Hello world!"},
        fixed_order=True,
        desc="Merge nested strings",
    ),
    Test(
        chunks=[
            {"usage": {"prompt_tokens": 1}},
            {"usage": {"prompt_tokens": 2}},
        ],
        expected={"usage": {"prompt_tokens": 2}},
        fixed_order=True,
        desc="Merge top-level usage",
    ),
    Test(
        chunks=[
            {"a": {"usage": {"prompt_tokens": 1}}},
            {"a": {"usage": {"prompt_tokens": 2}}},
        ],
        expected={"a": {"usage": {"prompt_tokens": 2}}},
        fixed_order=True,
        desc="Merge nested usage",
    ),
]


def test_deep_copy_for_non_indexed_lists():
    chunk_actual = {"list": [{"content": "hello"}]}
    chunk_expected = copy.deepcopy(chunk_actual)

    chunk = {}
    chunk = merge(chunk, chunk_actual)
    chunk["list"][0]["content"] += " world"

    assert chunk_actual == chunk_expected
    assert chunk == {"list": [{"content": "hello world"}]}


def test_deep_copy_for_indexed_lists():
    chunk_actual = {"list": [{"index": 0, "content": "hello"}]}
    chunk_expected = copy.deepcopy(chunk_actual)

    chunk = {}
    chunk = merge(chunk, chunk_actual)
    chunk = merge(chunk, {"list": [{"index": 0, "content": " world"}]})

    assert chunk_actual == chunk_expected
    assert chunk == {"list": [{"index": 0, "content": "hello world"}]}


def test_deep_copy_for_dict_values():
    chunk_actual = {"a": {}}
    chunk_expected = copy.deepcopy(chunk_actual)

    chunk = {}
    chunk = merge(chunk, chunk_actual)
    chunk = merge(chunk, {"a": {"b": "c"}})

    assert chunk_actual == chunk_expected
    assert chunk == {"a": {"b": "c"}}


OPEN_CHUNK = create_single_choice_chunk(
    delta={"role": "assistant", "content": None}
)
CONTENT_CHUNK1 = create_single_choice_chunk(delta={"content": "hello"})
CONTENT_CHUNK2 = create_single_choice_chunk(delta={"content": " world"})


merge_chat_completion_chunks_cases: list[Test] = [
    Test(
        chunks=[1, 2],
        expected=Exception(
            "The chat completion chunks are expected to be dictionaries"
        ),
        desc="Non-dict chunk",
    ),
    Test(
        chunks=[],
        expected=Exception(
            "At least one chat completion chunk must be provided"
        ),
        desc="Zero chunks",
    ),
    Test(
        chunks=[OPEN_CHUNK, {}],
        expected=OPEN_CHUNK,
        desc="Merge with empty dict",
    ),
    Test(
        chunks=[OPEN_CHUNK, CONTENT_CHUNK1],
        expected=create_single_choice_chunk(
            delta={"role": "assistant", "content": "hello"}
        ),
        desc="Merge open with one content chunk",
    ),
    Test(
        chunks=[OPEN_CHUNK, CONTENT_CHUNK1, CONTENT_CHUNK2],
        order_constraints=[BeforeIdx(1, 2)],
        expected=create_single_choice_chunk(
            delta={"role": "assistant", "content": "hello world"}
        ),
        desc="Merge open with two content chunks",
    ),
    Test(
        chunks=[
            OPEN_CHUNK,  # 0
            create_single_choice_chunk(
                delta={"content": "sure, I'm calling the tools"}
            ),  # 1
            create_tool_call_chunk(
                0,
                id="tool_call_1",
                name="get_weather",
                type="function",
            ),  # 2
            create_tool_call_chunk(0, arguments='{"cit'),  # 3
            create_tool_call_chunk(0, arguments='y": "London"}'),  # 4
            create_tool_call_chunk(
                1, id="tool_call_2", name="get_time", type="function"
            ),  # 5
            create_tool_call_chunk(1, arguments="{}"),  # 6
        ],
        order_constraints=[Fixed(0), BeforeIdx(3, 4)],
        expected=create_single_choice_chunk(
            delta={
                "role": "assistant",
                "content": "sure, I'm calling the tools",
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "tool_call_1",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"city": "London"}',
                        },
                    },
                    {
                        "index": 1,
                        "id": "tool_call_2",
                        "type": "function",
                        "function": {"name": "get_time", "arguments": "{}"},
                    },
                ],
            }
        ),
        desc="Merge with tool calls",
    ),
    Test(
        chunks=[
            create_single_choice_chunk(
                choice_idx=1, delta={"content": "5", "role": "assistant"}
            ),
            create_single_choice_chunk(
                choice_idx=0, delta={"content": "5", "role": "assistant"}
            ),
            create_single_choice_chunk(
                choice_idx=1,
                delta={},
                finish_reason="stop",
            ),
            create_single_choice_chunk(
                choice_idx=0,
                delta={},
                finish_reason="stop",
            ),
        ],
        expected=create_chunk(
            id="test_id",
            created=0,
            choices=[
                {
                    "index": i,
                    "delta": {"role": "assistant", "content": "5"},
                    "finish_reason": "stop",
                }
                for i in range(2)
            ],
        ),
        desc="Multiple choices",
    ),
]


@pytest.mark.parametrize(
    "test", permute(merge_chunks_cases), ids=attrgetter("desc")
)
def test_merge_chunks(test: Test):
    run_merge_test(test, merger=merge, remove_indices=True)


@pytest.mark.parametrize(
    "test", permute(merge_chat_completion_chunks_cases), ids=attrgetter("desc")
)
def test_merge_chat_completion_chunks(test: Test):
    run_merge_test(
        test, merger=merge_chat_completion_chunks, remove_indices=False
    )


def run_merge_test(
    test: Test, *, merger: Callable[[Any], Any], remove_indices: bool
):
    def _merge_chunks():
        old_chunks = [copy.deepcopy(chunk) for chunk in test.chunks]
        old_ids = [id(chunk) for chunk in test.chunks]

        merged = merger(*test.chunks)
        if remove_indices:
            merged = cleanup_indices(merged)

        new_chunks = test.chunks
        new_ids = [id(chunk) for chunk in test.chunks]

        assert old_chunks[1:] == new_chunks[1:]
        assert old_ids[1:] == new_ids[1:]

        for new_chunk in new_chunks[1:]:
            assert (
                collect_shared_mutable_objects(new_chunks[0], new_chunk)
                == set()
            )

        return merged

    if isinstance(test.expected, Exception):
        with pytest.raises(
            type(test.expected), match=re.escape(str(test.expected))
        ):
            _merge_chunks()
    else:
        assert _merge_chunks() == test.expected
