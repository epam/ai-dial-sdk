import pytest

from aidial_sdk._pydantic import SecretStr, ValidationError
from aidial_sdk.deployment.from_request_mixin import FromRequestDeploymentMixin
from tests.utils.constants import _DUMMY_FASTAPI_REQUEST
from tests.utils.pydantic import model_parse


def _create_request(**kwargs) -> FromRequestDeploymentMixin:
    data = {
        "original_request": _DUMMY_FASTAPI_REQUEST,
        "deployment_id": "test",
        "headers": {},
        **kwargs,
    }
    return model_parse(FromRequestDeploymentMixin, data)


def test_create_secrets_api_key_converted():
    obj = _create_request(api_key="test-api-key")
    assert obj.api_key_secret.get_secret_value() == "test-api-key"
    assert obj.api_key == "test-api-key"


def test_create_secrets_api_key_passthrough():
    obj = _create_request(api_key_secret=SecretStr("test-api-key"))
    assert obj.api_key_secret.get_secret_value() == "test-api-key"
    assert obj.api_key == "test-api-key"


def test_create_secrets_api_key_conflict_raises():
    with pytest.raises(
        ValidationError,
        match="api_key and api_key_secret cannot be both provided",
    ):
        _create_request(
            api_key="test-api-key",
            api_key_secret=SecretStr("test-api-key"),
        )


def test_create_secrets_jwt_converted():
    obj = _create_request(api_key="test-api-key", jwt="Bearer tok")
    assert isinstance(obj.jwt_secret, SecretStr)
    assert obj.jwt_secret.get_secret_value() == "Bearer tok"
    assert obj.bearer_token_secret is not None
    assert obj.bearer_token_secret.get_secret_value() == "tok"
    assert obj.bearer_token == "tok"  # noqa: S105


def test_create_secrets_jwt_conflict_raises():
    with pytest.raises(
        ValidationError,
        match="jwt and jwt_secret cannot be both provided",
    ):
        _create_request(
            api_key="test-api-key",
            jwt="Bearer tok",
            jwt_secret=SecretStr("Bearer tok"),
        )
