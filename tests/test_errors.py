import dataclasses
from typing import Any, Dict, List

import pytest

from tests.applications.broken import (
    ImmediatelyBrokenApplication,
    RuntimeBrokenApplication,
)
from tests.applications.noop import NoopApplication
from tests.utils.chunks import check_sse_stream, create_single_choice_chunk
from tests.utils.client import create_app_client

DEFAULT_RUNTIME_ERROR = {
    "error": {
        "message": "Error during processing the request",
        "type": "runtime_error",
        "code": "500",
    }
}

API_KEY_IS_MISSING = {
    "error": {
        "message": "Api-Key header is required",
        "type": "invalid_request_error",
        "code": "400",
    }
}


@dataclasses.dataclass
class ErrorTestCase:
    content: Any
    response_code: int
    response_error: dict
    response_headers: Dict[str, str] = dataclasses.field(default_factory=dict)


error_testcases: List[ErrorTestCase] = [
    ErrorTestCase("fastapi_exception", 500, DEFAULT_RUNTIME_ERROR),
    ErrorTestCase("value_error_exception", 500, DEFAULT_RUNTIME_ERROR),
    ErrorTestCase("zero_division_exception", 500, DEFAULT_RUNTIME_ERROR),
    ErrorTestCase(
        "sdk_exception",
        503,
        {
            "error": {
                "message": "Test error",
                "type": "runtime_error",
                "code": "503",
            }
        },
    ),
    ErrorTestCase(
        "sdk_exception_with_display_message",
        503,
        {
            "error": {
                "message": "Test error",
                "type": "runtime_error",
                "display_message": "I'm broken",
                "code": "503",
            }
        },
    ),
    ErrorTestCase(
        None,
        400,
        {
            "error": {
                "message": "Unable to retrieve text content of the message: the actual content is null or missing.",
                "type": "invalid_request_error",
                "code": "400",
            }
        },
    ),
    ErrorTestCase(
        [{"type": "text", "text": "hello"}],
        400,
        {
            "error": {
                "message": "Unable to retrieve text content of the message: the actual content is a list of content parts.",
                "type": "invalid_request_error",
                "code": "400",
            }
        },
    ),
    ErrorTestCase(
        "sdk_exception_with_headers",
        429,
        {
            "error": {
                "message": "Too many requests",
                "type": "runtime_error",
                "code": "429",
            }
        },
        {"Retry-after": "42"},
    ),
]


@pytest.mark.parametrize("test_case", error_testcases)
def test_error(test_case: ErrorTestCase):
    client = create_app_client(ImmediatelyBrokenApplication())

    response = client.post(
        "chat/completions",
        json={
            "messages": [{"role": "user", "content": test_case.content}],
            "stream": False,
        },
        headers={"Api-Key": "TEST_API_KEY"},
    )

    assert response.status_code == test_case.response_code
    assert response.json() == test_case.response_error

    for k, v in test_case.response_headers.items():
        assert response.headers.get(k) == v


@pytest.mark.parametrize("test_case", error_testcases)
def test_streaming_error(test_case: ErrorTestCase):
    client = create_app_client(ImmediatelyBrokenApplication())

    response = client.post(
        "chat/completions",
        json={
            "messages": [{"role": "user", "content": test_case.content}],
            "stream": True,
        },
        headers={"Api-Key": "TEST_API_KEY"},
    )

    assert response.status_code == test_case.response_code
    assert response.json() == test_case.response_error


@pytest.mark.parametrize("test_case", error_testcases)
def test_runtime_streaming_error(test_case: ErrorTestCase):
    client = create_app_client(RuntimeBrokenApplication())

    response = client.post(
        "chat/completions",
        json={
            "messages": [{"role": "user", "content": test_case.content}],
            "stream": True,
        },
    )

    check_sse_stream(
        response.iter_lines(),
        [
            create_single_choice_chunk({"role": "assistant"}),
            create_single_choice_chunk({"content": "Test content"}),
            create_single_choice_chunk({}, "stop"),
            test_case.response_error,
        ],
    )


def test_no_api_key():
    client = create_app_client(NoopApplication(), headers={})

    response = client.post(
        "chat/completions",
        json={
            "messages": [{"role": "user", "content": "test"}],
            "stream": False,
        },
    )

    assert response.status_code == 400
    assert response.json() == API_KEY_IS_MISSING
