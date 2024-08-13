import json

import pytest
from starlette.testclient import TestClient

from aidial_sdk import DIALApp
from tests.applications.broken_immediately import BrokenApplication
from tests.applications.broken_in_runtime import RuntimeBrokenApplication
from tests.applications.noop import NoopApplication

DEFAULT_RUNTIME_ERROR = {
    "error": {
        "message": "Error during processing the request",
        "type": "runtime_error",
    }
}

API_KEY_IS_MISSING = {
    "error": {
        "message": "Api-Key header is required",
        "type": "invalid_request_error",
        "code": "400",
    }
}

error_testdata = [
    ("fastapi_exception", 500, DEFAULT_RUNTIME_ERROR),
    ("value_error_exception", 500, DEFAULT_RUNTIME_ERROR),
    ("zero_division_exception", 500, DEFAULT_RUNTIME_ERROR),
    (
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
    (
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
]


@pytest.mark.parametrize(
    "type, response_status_code, response_content", error_testdata
)
def test_error(type, response_status_code, response_content):
    dial_app = DIALApp()
    dial_app.add_chat_completion("test_app", BrokenApplication())

    test_app = TestClient(dial_app)

    response = test_app.post(
        "/openai/deployments/test_app/chat/completions",
        json={
            "messages": [{"role": "user", "content": type}],
            "stream": False,
        },
        headers={"Api-Key": "TEST_API_KEY"},
    )

    assert (
        response.status_code == response_status_code
        and response.json() == response_content
    )


@pytest.mark.parametrize(
    "type, response_status_code, response_content", error_testdata
)
def test_streaming_error(type, response_status_code, response_content):
    dial_app = DIALApp()
    dial_app.add_chat_completion("test_app", BrokenApplication())

    test_app = TestClient(dial_app)

    response = test_app.post(
        "/openai/deployments/test_app/chat/completions",
        json={
            "messages": [{"role": "user", "content": type}],
            "stream": True,
        },
        headers={"Api-Key": "TEST_API_KEY"},
    )

    assert (
        response.status_code == response_status_code
        and response.json() == response_content
    )


@pytest.mark.parametrize(
    "type, response_status_code, response_content", error_testdata
)
def test_runtime_streaming_error(type, response_status_code, response_content):
    dial_app = DIALApp()
    dial_app.add_chat_completion("test_app", RuntimeBrokenApplication())

    test_app = TestClient(dial_app)

    response = test_app.post(
        "/openai/deployments/test_app/chat/completions",
        json={
            "messages": [{"role": "user", "content": type}],
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
            assert json.loads(data) == response_content
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

    assert response.status_code == 400 and response.json() == API_KEY_IS_MISSING
