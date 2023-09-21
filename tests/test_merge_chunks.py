import re
from dataclasses import dataclass
from typing import Any, List, Union

import pytest

from aidial_sdk.utils.merge_chunks import (
    CANNOT_MERGE_NON_INDEXED_AND_INDEXED_LISTS_ERROR_MESSAGE,
    CANNOT_MERGE_NON_INDEXED_LISTS_ERROR_MESSAGE,
    INCONSISTENT_INDEXED_LIST_ERROR_MESSAGE,
    cleanup_indices,
    merge,
)


@dataclass
class Test:
    __test__ = False  # Hide from pytest test discovery

    chunks: List[Any]
    expected: Union[Any, Exception]
    desc: str


test_cases: List[Test] = [
    Test(chunks=[1, 2], expected=2, desc="Merge ints"),
    Test(chunks=[1.0, 2.0], expected=2.0, desc="Merge floats"),
    Test(chunks=["foo", "bar"], expected="foobar", desc="Merge strings"),
    Test(chunks=[True, False], expected=False, desc="Merge bools"),
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
        desc="str+int type-error",
    ),
    Test(
        chunks=[{"a": {"b": 1}}, {"a": {"b": "foo"}}],
        expected=TypeError(
            "Cannot merge 'int' with incoming 'str' at path $.a.b"
        ),
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
        desc="Inconsistent list indexing",
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
        chunks=[{"a": [1]}, {"a": [2]}],
        expected=AssertionError(CANNOT_MERGE_NON_INDEXED_LISTS_ERROR_MESSAGE),
        desc="Merge lists of non-dicts",
    ),
    Test(
        chunks=[{"a": [{"b": 1}]}, {"a": [{"b": 2}]}],
        expected=AssertionError(CANNOT_MERGE_NON_INDEXED_LISTS_ERROR_MESSAGE),
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
    ),
    Test(
        chunks=[
            {"a": [{"index": 0, "value": 1}]},
            {"a": [{"index": 0, "value": 2}]},
        ],
        expected={"a": [{"value": 2}]},
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
            {},
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
        chunks=[{"a": "Hello "}, {"a": "world!"}],
        expected={"a": "Hello world!"},
        desc="Merge nested strings",
    ),
    Test(
        chunks=[
            {"usage": {"prompt_tokens": 1}},
            {"usage": {"prompt_tokens": 2}},
        ],
        expected={"usage": {"prompt_tokens": 2}},
        desc="Merge top-level usage",
    ),
    Test(
        chunks=[
            {"a": {"usage": {"prompt_tokens": 1}}},
            {"a": {"usage": {"prompt_tokens": 2}}},
        ],
        expected={"a": {"usage": {"prompt_tokens": 2}}},
        desc="Merge nested usage",
    ),
]


@pytest.mark.parametrize("test", test_cases, ids=lambda t: t.desc)
def test_merge_chunks(test: Test):
    if isinstance(test.expected, Exception):
        with pytest.raises(
            type(test.expected), match=re.escape(str(test.expected))
        ):
            cleanup_indices(merge(*test.chunks))
    else:
        assert cleanup_indices(merge(*test.chunks)) == test.expected
