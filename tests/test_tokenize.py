from typing import List

import pytest

from tests.applications.echo_application import EchoApplication
from tests.applications.noop_application import NoopApplication
from tests.utils.endpoint_test import TestCase, run_endpoint_test
from tests.utils.errors import missing_fields_error, route_not_found_error

CHAT_COMPLETION_REQUEST = {
    "messages": [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "ping"},
        {"role": "assistant", "content": "pong"},
        {"role": "user", "content": "hello"},
    ],
}

TOKENIZE_REQUEST_OK1 = {
    "inputs": [
        {"type": "request", "value": CHAT_COMPLETION_REQUEST},
        {"type": "string", "value": "test string"},
    ]
}
TOKENIZE_RESPONSE_OK1 = {
    "outputs": [
        {"status": "success", "token_count": 4},
        {"status": "success", "token_count": 2},
    ]
}

TOKENIZE_REQUEST_OK2 = {"inputs": []}
TOKENIZE_RESPONSE_OK2 = {"outputs": []}

TOKENIZE_REQUEST_FAIL = {"inputs": [{}]}

noop = NoopApplication()
echo = EchoApplication

testcases: List[TestCase] = [
    TestCase(noop, "tokenize", TOKENIZE_REQUEST_OK1, route_not_found_error),
    TestCase(noop, "tokenizer", TOKENIZE_REQUEST_OK1, route_not_found_error),
    TestCase(echo(0), "tokenize", TOKENIZE_REQUEST_OK1, TOKENIZE_RESPONSE_OK1),
    TestCase(echo(0), "tokenize", TOKENIZE_REQUEST_OK2, TOKENIZE_RESPONSE_OK2),
    TestCase(
        echo(0),
        "tokenize",
        TOKENIZE_REQUEST_FAIL,
        missing_fields_error("inputs.0.value"),
    ),
]


@pytest.mark.parametrize("testcase", testcases)
def test_tokenize(testcase: TestCase):
    run_endpoint_test(testcase)
