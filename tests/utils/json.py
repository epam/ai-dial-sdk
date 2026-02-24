import re
from typing import Any


def match_objects(expected: Any, actual: Any) -> bool:
    if isinstance(expected, dict):
        assert sorted(expected.keys()) == sorted(actual.keys())
        for k, v in expected.items():
            match_objects(v, actual[k])
    elif isinstance(expected, tuple | list):
        assert len(expected) == len(actual)
        for i in range(len(expected)):
            match_objects(expected[i], actual[i])
    elif callable(expected):
        assert expected(actual)
    elif isinstance(expected, re.Pattern):
        assert expected.match(actual), (
            f"{actual!r} doesn't match the regex {expected.pattern!r}"
        )
    else:
        assert expected == actual

    return True
