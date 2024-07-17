from typing import List

import pytest

from aidial_sdk import DIALApp
from tests.applications.simple_embeddings import SimpleEmbeddings
from tests.utils.endpoint_test import TestCase, run_endpoint_test

deployment = "test-app"
app = DIALApp().add_embeddings(deployment, SimpleEmbeddings())

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
        app,
        deployment,
        "embeddings",
        {"input": "a", "custom_fields": {"type": "query"}},
        expected_response_1,
    ),
    TestCase(
        app,
        deployment,
        "embeddings",
        {"input": ["a", "b"]},
        expected_response_2,
    ),
]


@pytest.mark.parametrize("testcase", testcases)
def test_embeddings(testcase: TestCase):
    run_endpoint_test(testcase)
