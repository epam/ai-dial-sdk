from typing import List

import pytest

from aidial_sdk import DIALApp
from tests.applications.echo import EchoApplication
from tests.applications.noop import NoopApplication
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


deployment = "test-app"

noop = DIALApp().add_chat_completion(deployment, NoopApplication())

echo = DIALApp().add_chat_completion(deployment, EchoApplication(0))


testcases: List[TestCase] = [
    TestCase(
        noop,
        deployment,
        "tokenize",
        TOKENIZE_REQUEST_OK1,
        route_not_found_error,
    ),
    TestCase(
        noop,
        deployment,
        "tokenizer",
        TOKENIZE_REQUEST_OK1,
        route_not_found_error,
    ),
    TestCase(
        echo,
        deployment,
        "tokenize",
        TOKENIZE_REQUEST_OK1,
        TOKENIZE_RESPONSE_OK1,
    ),
    TestCase(
        echo,
        deployment,
        "tokenize",
        TOKENIZE_REQUEST_OK2,
        TOKENIZE_RESPONSE_OK2,
    ),
    TestCase(
        echo,
        deployment,
        "tokenize",
        TOKENIZE_REQUEST_FAIL,
        missing_fields_error("inputs.0.value"),
    ),
]


@pytest.mark.parametrize("testcase", testcases)
def test_tokenize(testcase: TestCase):
    run_endpoint_test(testcase)
