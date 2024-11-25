import pytest

from tests.applications.broken_immediately import BrokenApplication
from tests.applications.broken_in_runtime import RuntimeBrokenApplication
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
    (
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
    (
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
]


@pytest.mark.parametrize(
    "type, response_status_code, response_content", error_testdata
)
def test_error(type, response_status_code, response_content):
    client = create_app_client(BrokenApplication())

    response = client.post(
        "chat/completions",
        json={
            "messages": [{"role": "user", "content": type}],
            "stream": False,
        },
        headers={"Api-Key": "TEST_API_KEY"},
    )

    assert response.status_code == response_status_code
    assert response.json() == response_content


@pytest.mark.parametrize(
    "type, response_status_code, response_content", error_testdata
)
def test_streaming_error(type, response_status_code, response_content):
    client = create_app_client(BrokenApplication())

    response = client.post(
        "chat/completions",
        json={
            "messages": [{"role": "user", "content": type}],
            "stream": True,
        },
        headers={"Api-Key": "TEST_API_KEY"},
    )

    assert response.status_code == response_status_code
    assert response.json() == response_content


@pytest.mark.parametrize(
    "type, response_status_code, response_content", error_testdata
)
def test_runtime_streaming_error(type, response_status_code, response_content):
    client = create_app_client(RuntimeBrokenApplication())

    response = client.post(
        "chat/completions",
        json={
            "messages": [{"role": "user", "content": type}],
            "stream": True,
        },
    )

    check_sse_stream(
        list(response.iter_lines()),
        [
            create_single_choice_chunk({"role": "assistant"}),
            create_single_choice_chunk({"content": "Test content"}),
            create_single_choice_chunk({}, "stop"),
            response_content,
        ],
    )


def test_no_api_key():
    client = create_app_client(NoopApplication(), api_key=None)

    response = client.post(
        "chat/completions",
        json={
            "messages": [{"role": "user", "content": "test"}],
            "stream": False,
        },
    )

    assert response.status_code == 400
    assert response.json() == API_KEY_IS_MISSING
