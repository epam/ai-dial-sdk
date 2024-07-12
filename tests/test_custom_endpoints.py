from typing import List

import pytest

from tests.applications.custom_endpoints import app
from tests.utils.endpoint_test import TestCase, run_endpoint_test
from tests.utils.errors import route_not_found_error

CHAT_COMPLETION_REQUEST = {"messages": [{"role": "user", "content": "ping"}]}

deployment = "test-app"

testcases: List[TestCase] = [
    TestCase(
        app,
        "test-app1",
        "tokenize",
        {"inputs": []},
        {"outputs": []},
    ),
    TestCase(
        app,
        "test-app1",
        "tokenizer",
        {},
        route_not_found_error,
    ),
    TestCase(
        app,
        "test-app1",
        "truncate_prompt",
        {},
        {"result": "custom_truncate_prompt_result"},
    ),
    TestCase(
        app,
        "test-app2",
        "chat/completions",
        {},
        {"result": "custom_chat_completion_result"},
    ),
    TestCase(
        app,
        "test-app2",
        "tokenize",
        {},
        route_not_found_error,
    ),
]


@pytest.mark.parametrize("testcase", testcases)
def test_custom_endpoints(testcase: TestCase):
    run_endpoint_test(testcase)
