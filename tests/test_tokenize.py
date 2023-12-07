from typing import List

import pytest

from tests.applications.echo_application import EchoApplication
from tests.applications.noop_application import NoopApplication
from tests.utils.endpoint_test import TestCase, run_endpoint_test
from tests.utils.errors import (
    bad_request_error,
    not_implemented_error,
    route_not_found_error,
)

CHAT_COMPLETION_REQUEST = {
    "messages": [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "ping"},
        {"role": "assistant", "content": "pong"},
        {"role": "user", "content": "hello"},
    ],
}

TOKENIZE_REQUEST_OK1 = {"requests": [CHAT_COMPLETION_REQUEST, "test string"]}
TOKENIZE_RESPONSE_OK1 = {
    "responses": [
        {"status": "success", "token_count": 4},
        {"status": "success", "token_count": 2},
    ]
}

TOKENIZE_REQUEST_OK2 = {"requests": []}
TOKENIZE_RESPONSE_OK2 = {"responses": []}

TOKENIZE_REQUEST_FAIL = {"requests": [{}]}
TOKENIZE_RESPONSE_FAIL = {
    "responses": [
        {
            "status": "error",
            "error": "Request must contain either 'requests' or 'request'",
        }
    ]
}

noop = NoopApplication()
echo = EchoApplication

testcases: List[TestCase] = [
    TestCase(
        noop,
        "tokenize",
        TOKENIZE_REQUEST_OK1,
        not_implemented_error("tokenize"),
    ),
    TestCase(noop, "tokenizer", TOKENIZE_REQUEST_OK1, route_not_found_error),
    TestCase(echo(0), "tokenize", TOKENIZE_REQUEST_OK1, TOKENIZE_RESPONSE_OK1),
    TestCase(echo(0), "tokenize", TOKENIZE_REQUEST_OK2, TOKENIZE_RESPONSE_OK2),
    TestCase(
        echo(0),
        "tokenize",
        TOKENIZE_REQUEST_FAIL,
        bad_request_error("requests.0.messages"),
    ),
]


@pytest.mark.parametrize("testcase", testcases)
def test_tokenize(testcase: TestCase):
    run_endpoint_test(testcase)
