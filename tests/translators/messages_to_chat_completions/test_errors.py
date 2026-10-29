import json
from typing import Never

import httpx
import openai
import pytest
from pydantic import BaseModel

from aidial_sdk.translators.messages_to_chat_completions.errors import (
    AnthropicErrorType,
    AnthropicHTTPError,
    anthropic_error_from_upstream,
    anthropic_error_response,
    translator_error_handler,
)


def _status_error(
    status: int, body: object | None, message: str
) -> openai.APIStatusError:
    request = httpx.Request("POST", "http://core/openai/v1/responses")
    return openai.APIStatusError(
        message, response=httpx.Response(status, request=request), body=body
    )


@pytest.mark.parametrize(
    "status, expected",
    [
        (400, "invalid_request_error"),
        (422, "invalid_request_error"),
        (401, "authentication_error"),
        (403, "permission_error"),
        (404, "not_found_error"),
        (413, "request_too_large"),
        (429, "rate_limit_error"),
        (500, "api_error"),
        (502, "api_error"),
        (503, "overloaded_error"),
        (529, "overloaded_error"),
        (418, "api_error"),
    ],
)
def test_upstream_error_preserves_status_and_maps_type(
    status: int, expected: str
) -> None:
    response = anthropic_error_from_upstream(
        _status_error(status, {"message": "upstream failure"}, "fallback")
    )
    assert response.status_code == status
    assert json.loads(bytes(response.body)) == {
        "type": "error",
        "error": {"type": expected, "message": "upstream failure"},
    }


@pytest.mark.parametrize(
    "error_type, status, code",
    [
        (AnthropicErrorType.INVALID_REQUEST, 400, "invalid_request_error"),
        (AnthropicErrorType.AUTHENTICATION, 401, "authentication_error"),
        (AnthropicErrorType.PERMISSION, 403, "permission_error"),
        (AnthropicErrorType.NOT_FOUND, 404, "not_found_error"),
        (AnthropicErrorType.REQUEST_TOO_LARGE, 413, "request_too_large"),
        (AnthropicErrorType.RATE_LIMIT, 429, "rate_limit_error"),
        (AnthropicErrorType.API, 500, "api_error"),
        (AnthropicErrorType.OVERLOADED, 529, "overloaded_error"),
    ],
)
def test_local_error_uses_enum_default_status(
    error_type: AnthropicErrorType, status: int, code: str
) -> None:
    error = AnthropicHTTPError(error_type, "local failure")
    assert error.status_code == status
    assert error.error_type is error_type
    assert str(error) == "local failure"
    response = anthropic_error_response(error.error_type, error.message)
    assert response.status_code == status
    assert json.loads(bytes(response.body)) == {
        "type": "error",
        "error": {"type": code, "message": "local failure"},
    }


@pytest.mark.parametrize(
    "body, expected",
    [
        (
            {
                "error": {"message": "nested error"},
                "message": "top-level error",
            },
            "nested error",
        ),
        ({"error": "string error"}, "string error"),
        ({"message": "top-level error"}, "top-level error"),
        ("raw error", "raw error"),
        ("", "SDK fallback"),
    ],
)
def test_upstream_error_message(body: object, expected: str) -> None:
    response = anthropic_error_from_upstream(
        _status_error(400, body, "SDK fallback")
    )
    assert response.status_code == 400
    assert json.loads(bytes(response.body)) == {
        "type": "error",
        "error": {"type": "invalid_request_error", "message": expected},
    }


async def test_translator_error_handler_maps_unexpected_exception_to_500() -> (
    None
):
    @translator_error_handler
    async def _handler() -> Never:
        raise RuntimeError("totally unexpected")

    response = await _handler()

    assert response.status_code == 500
    body = json.loads(bytes(response.body))
    assert body["error"]["type"] == "api_error"
    assert body["error"]["message"] == "Internal server error"


class _StrictIntModel(BaseModel):
    x: int


async def test_internal_pydantic_validation_error_is_a_500() -> None:
    @translator_error_handler
    async def _handler() -> Never:
        _StrictIntModel.model_validate({"x": "not-an-int"})
        raise AssertionError("model_validate should have raised")

    response = await _handler()

    assert response.status_code == 500
    body = json.loads(bytes(response.body))
    assert body["error"]["type"] == "api_error"
    assert body["error"]["message"] == "Internal server error"
