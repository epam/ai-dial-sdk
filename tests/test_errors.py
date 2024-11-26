import dataclasses
import json
from typing import Any, Dict, List

import pytest
from starlette.testclient import TestClient

from aidial_sdk import DIALApp
from tests.applications.broken import (
    ImmediatelyBrokenApplication,
    RuntimeBrokenApplication,
)
from tests.applications.noop import NoopApplication

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
    dial_app = DIALApp()
    dial_app.add_chat_completion("test_app", ImmediatelyBrokenApplication())

    test_app = TestClient(dial_app)

    response = test_app.post(
        "/openai/deployments/test_app/chat/completions",
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
    dial_app = DIALApp()
    dial_app.add_chat_completion("test_app", ImmediatelyBrokenApplication())

    test_app = TestClient(dial_app)

    response = test_app.post(
        "/openai/deployments/test_app/chat/completions",
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
    dial_app = DIALApp()
    dial_app.add_chat_completion("test_app", RuntimeBrokenApplication())

    test_app = TestClient(dial_app)

    response = test_app.post(
        "/openai/deployments/test_app/chat/completions",
        json={
            "messages": [{"role": "user", "content": test_case.content}],
            "stream": True,
        },
        headers={"Api-Key": "TEST_API_KEY"},
    )

    for index, value in enumerate(response.iter_lines()):
        if index % 2:
            assert value == ""
            continue

        assert value.startswith("data: ")
        data = value[6:]

        if index == 0:
            assert json.loads(data) == {
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": None,
                        "delta": {"role": "assistant"},
                    }
                ],
                "usage": None,
                "id": "test_id",
                "created": 0,
                "object": "chat.completion.chunk",
            }
        elif index == 2:
            assert json.loads(data) == {
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": None,
                        "delta": {"content": "Test content"},
                    }
                ],
                "usage": None,
                "id": "test_id",
                "created": 0,
                "object": "chat.completion.chunk",
            }
        elif index == 4:
            assert json.loads(data) == {
                "choices": [{"index": 0, "finish_reason": "stop", "delta": {}}],
                "usage": None,
                "id": "test_id",
                "created": 0,
                "object": "chat.completion.chunk",
            }
        elif index == 6:
            assert json.loads(data) == test_case.response_error
        elif index == 8:
            assert data == "[DONE]"


def test_no_api_key():
    dial_app = DIALApp()
    dial_app.add_chat_completion("test_app", NoopApplication())

    test_app = TestClient(dial_app)

    response = test_app.post(
        "/openai/deployments/test_app/chat/completions",
        json={
            "messages": [{"role": "user", "content": "test"}],
            "stream": False,
        },
    )

    assert response.status_code == 400
    assert response.json() == API_KEY_IS_MISSING
