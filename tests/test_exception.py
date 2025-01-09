from typing import List, Tuple

import pytest

from aidial_sdk.exceptions import HTTPException, TruncatePromptSystemError

test_cases: List[Tuple[HTTPException, str]] = [
    (
        HTTPException(
            message="message",
            status_code=400,
            type="type",
            param="param",
            code="code",
            display_message="display_message",
            headers={"header": "value"},
        ),
        "message",
    ),
    (
        TruncatePromptSystemError(1, 20),
        "The requested maximum prompt tokens is 1. "
        "However, the system messages resulted in 20 tokens. "
        "Please reduce the length of the system messages or increase the maximum prompt tokens.",
    ),
]


@pytest.mark.parametrize("exc, expected", test_cases)
def test_str_exception(exc: HTTPException, expected: str):
    assert str(exc) == expected
