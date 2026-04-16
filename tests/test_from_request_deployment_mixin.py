import json

import fastapi
import pytest

from aidial_sdk.deployment.from_request_mixin import FromRequestDeploymentMixin
from aidial_sdk.exceptions import InvalidRequestError


def _make_request(
    headers: dict[str, str], body: dict | None = None
) -> fastapi.Request:
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    scope = {
        "type": "http",
        "method": "POST",
        "headers": raw_headers,
        "query_string": b"",
    }
    body_bytes = json.dumps(body or {}).encode()

    async def receive():
        return {"type": "http.request", "body": body_bytes}

    return fastapi.Request(scope, receive)


async def _from_request(headers: dict[str, str]) -> FromRequestDeploymentMixin:
    return await FromRequestDeploymentMixin.from_request(
        _make_request(headers),
        deployment_id="test-deployment-id",
        base_url=None,
    )


async def test_api_key_extracted():
    obj = await _from_request({"api-key": "my-key"})
    assert obj.api_key_secret.get_secret_value() == "my-key"
    assert obj.api_key == "my-key"


async def test_api_key_missing_raises():
    with pytest.raises(InvalidRequestError, match="Api-Key header is required"):
        await _from_request({})


async def test_bearer_authorization_extracted():
    obj = await _from_request(
        {"api-key": "my-key", "authorization": "Bearer tok"}
    )

    assert obj.jwt_secret is not None
    assert obj.jwt_secret.get_secret_value() == "Bearer tok"

    assert obj.bearer_token_secret is not None
    assert obj.bearer_token_secret.get_secret_value() == "tok"
    assert obj.bearer_token == "tok"  # noqa: S105


async def test_no_authorization_header():
    obj = await _from_request({"api-key": "my-key"})
    assert obj.jwt_secret is None
    assert obj.bearer_token_secret is None
    assert obj.bearer_token is None


async def test_non_bearer_authorization_header():
    obj = await _from_request(
        {"api-key": "my-key", "authorization": "Token custom"}
    )
    assert obj.jwt_secret is not None
    assert obj.jwt_secret.get_secret_value() == "Token custom"
    assert obj.bearer_token is None
