from typing import List

import pytest

from tests.applications.simple_embeddings import SimpleEmbeddings
from tests.utils.endpoint_test import TestCase, run_endpoint_test
from tests.utils.errors import Error

simple = SimpleEmbeddings()

expected_response_1 = {
    "data": [
        {"embedding": [0.0], "index": 0, "object": "embedding"},
    ],
    "model": "dummy",
    "object": "list",
    "usage": {"prompt_tokens": 1, "total_tokens": 1},
}

expected_response_2 = {
    "data": [
        {"embedding": [0.0], "index": 0, "object": "embedding"},
        {"embedding": [1.0], "index": 1, "object": "embedding"},
    ],
    "model": "dummy",
    "object": "list",
    "usage": {"prompt_tokens": 2, "total_tokens": 2},
}

testcases: List[TestCase] = [
    TestCase(
        simple,
        "embeddings",
        {"input": "a"},
        expected_response_1,
        {"X-DIAL-Type": "query"},
    ),
    TestCase(
        simple,
        "embeddings",
        {"input": "a"},
        Error(
            code=400,
            error={
                "error": {
                    "message": "Invalid value 'hello' for 'X-DIAL-Type' header. Valid "
                    "values are: ['symmetric', 'document', 'query']",
                    "type": "invalid_request_error",
                }
            },
        ),
        {"X-DIAL-Type": "hello"},
    ),
    TestCase(
        simple,
        "embeddings",
        {"input": ["a", "b"]},
        expected_response_2,
    ),
]


@pytest.mark.parametrize("testcase", testcases)
def test_embeddings(testcase: TestCase):
    run_endpoint_test(testcase)
