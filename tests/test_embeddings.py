import pytest

from aidial_sdk import DIALApp
from aidial_sdk.embeddings.request import EmbeddingsRequest
from tests.applications.simple_embeddings import SimpleEmbeddings
from tests.utils.endpoint_test import TestCase, run_endpoint_test
from tests.utils.pydantic import model_parse

deployment = "test-app"
app = DIALApp().add_embeddings(deployment, SimpleEmbeddings())


def _expected_response(n: int) -> dict:
    return {
        "data": [
            {"embedding": [float(i)], "index": i, "object": "embedding"}
            for i in range(n)
        ],
        "model": "dummy",
        "object": "list",
        "usage": {"prompt_tokens": n, "total_tokens": n},
    }


testcases: list[TestCase] = [
    TestCase(
        app,
        deployment,
        "embeddings",
        {
            "input": "a",
            "custom_fields": {
                "type": "query",
                "instruction": "instruction",
            },
        },
        _expected_response(1),
    ),
    TestCase(
        app,
        deployment,
        "embeddings",
        {"input": [15339]},
        _expected_response(1),
    ),
    TestCase(
        app,
        deployment,
        "embeddings",
        {"input": ["a", "b"]},
        _expected_response(2),
    ),
    TestCase(
        app,
        deployment,
        "embeddings",
        {
            "input": ["a"],
            "custom_input": [
                "input0",
                ["input1"],
                ["input2-part1", "input2-part2"],
                {
                    "type": "text/plain",
                    "data": "attachment data1",
                },
                [
                    "attachment title",
                    {
                        "type": "text/plain",
                        "data": "attachment data2",
                    },
                ],
            ],
            "custom_fields": {"instruction": "instruction"},
        },
        _expected_response(1),
    ),
]


@pytest.mark.parametrize("testcase", testcases)
def test_embeddings_call(testcase: TestCase):
    run_endpoint_test(testcase)


@pytest.mark.parametrize("testcase", testcases)
def test_embeddings_request_parsing(testcase: TestCase):
    request = testcase.request_body
    request.setdefault("encoding_format", "float")

    parsed = model_parse(EmbeddingsRequest, request)
    assert parsed.model_dump(exclude_none=True) == request
