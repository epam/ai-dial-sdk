import json
from typing import Never

import httpx
import pytest
import respx
from fastapi import Request, Response
from pydantic import BaseModel, ValidationError

from aidial_sdk._errors import error_handler
from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.translators.messages_to_chat_completions.backend.http import (
    ChatClientHttp,
    core_v1_client,
)


async def _anthropic_error(error: Exception) -> Response:
    @error_handler("anthropic")
    async def _handler(request: Request) -> Never:
        raise error

    return await _handler(Request({"type": "http"}))


async def _core_error(status: int, body: dict | str) -> DIALException:
    response = (
        httpx.Response(status, json=body)
        if isinstance(body, dict)
        else httpx.Response(status, text=body)
    )
    with respx.mock:
        respx.post("http://core/openai/v1/chat/completions").mock(response)
        async with httpx.AsyncClient() as http_client:
            client = ChatClientHttp(
                core_v1_client("http://core", http_client),
                core_headers={},
                heartbeat_interval=None,
            )
            with pytest.raises(DIALException) as e:
                await client.create_block({})
    return e.value


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
async def test_upstream_error_preserves_status_and_maps_type(
    status: int, expected: str
) -> None:
    response = await _anthropic_error(
        await _core_error(status, {"message": "upstream failure"})
    )
    assert response.status_code == status
    assert json.loads(bytes(response.body)) == {
        "type": "error",
        "error": {"type": expected, "message": "upstream failure"},
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
        ("", "Error code: 400"),
    ],
)
async def test_upstream_error_message(body: dict | str, expected: str) -> None:
    response = await _anthropic_error(await _core_error(400, body))
    assert response.status_code == 400
    assert json.loads(bytes(response.body)) == {
        "type": "error",
        "error": {"type": "invalid_request_error", "message": expected},
    }


async def test_an_unexpected_exception_is_a_500() -> None:
    response = await _anthropic_error(RuntimeError("totally unexpected"))

    assert response.status_code == 500
    body = json.loads(bytes(response.body))
    assert body["error"]["type"] == "api_error"
    assert body["error"]["message"] == "Internal server error"


class _StrictIntModel(BaseModel):
    x: int


async def test_internal_pydantic_validation_error_is_a_500() -> None:
    with pytest.raises(ValidationError) as exc:
        _StrictIntModel.model_validate({"x": "not-an-int"})

    response = await _anthropic_error(exc.value)

    assert response.status_code == 500
    body = json.loads(bytes(response.body))
    assert body["error"]["type"] == "api_error"
    assert body["error"]["message"] == "Internal server error"
