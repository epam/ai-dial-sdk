import json
from typing import Any
from unittest.mock import MagicMock, patch

import fastapi
import pytest
import respx
from pydantic.v1 import StrictStr
from starlette.datastructures import MutableHeaders
from starlette.testclient import TestClient

from aidial_sdk import DIALApp, HTTPException
from aidial_sdk.chat_completion import ChatCompletion, Request, Response
from aidial_sdk.deployment.configuration import (
    ConfigurationRequest,
    ConfigurationResponse,
)
from aidial_sdk.deployment.from_request_mixin import FromRequestDeploymentMixin
from aidial_sdk.deployment.rate import RateRequest
from aidial_sdk.deployment.tokenize import TokenizeRequest, TokenizeResponse
from aidial_sdk.deployment.truncate_prompt import (
    TruncatePromptRequest,
    TruncatePromptResponse,
)
from aidial_sdk.exceptions import InternalServerError
from aidial_sdk.pydantic_v1 import SecretStr


class TestApp(ChatCompletion):
    @staticmethod
    async def assert_request_data(request: FromRequestDeploymentMixin) -> None:
        if request.unreliable_dial_application_properties is not None:
            assert request.unreliable_dial_application_properties == {
                "key1": "value1",
                "key2": "value2",
            }
        else:
            application_properties = (
                await request.request_dial_application_properties()
            )
            assert application_properties == {
                "key1": "value1",
                "key2": "value2",
            }

    async def chat_completion(self, request: Request, response: Response):
        await self.assert_request_data(request)
        with response.create_choice() as choice:
            choice.append_content("Hello")

    async def configuration(self, request: ConfigurationRequest):
        await self.assert_request_data(request)
        return ConfigurationResponse()

    async def rate_response(self, request: RateRequest):
        await self.assert_request_data(request)

    async def tokenize(self, request: TokenizeRequest):
        await self.assert_request_data(request)
        return TokenizeResponse(outputs=[])

    async def truncate_prompt(self, request: TruncatePromptRequest):
        await self.assert_request_data(request)
        return TruncatePromptResponse(outputs=[])


DEPLOYMENT_NAME = "test-app"
API_KEY = "test-api-key"
X_APPLICATION_ID = "test-app"


@pytest.fixture
def mock_app_props():
    with respx.mock() as mock:
        mock.get(
            f"https://test.com/openai/applications/{X_APPLICATION_ID}"
        ).respond(
            status_code=200,
            json={
                "application_properties": {"key1": "value1", "key2": "value2"}
            },
        )
        yield mock


@pytest.fixture
def mock_app_props_error():
    with respx.mock() as mock:
        mock.get(
            f"https://test.com/openai/applications/{X_APPLICATION_ID}"
        ).respond(status_code=500)
        yield mock


@pytest.fixture
def client():
    app = DIALApp(dial_url="https://test.com").add_chat_completion(
        DEPLOYMENT_NAME, TestApp()
    )
    yield TestClient(
        app,
        base_url=f"https://testserver/openai/deployments/{DEPLOYMENT_NAME}",
        headers={"Api-Key": API_KEY},
    )


@pytest.fixture
def client_without_base_url():
    app = DIALApp().add_chat_completion(DEPLOYMENT_NAME, TestApp())
    yield TestClient(
        app,
        base_url=f"https://testserver/openai/deployments/{DEPLOYMENT_NAME}",
        headers={"Api-Key": API_KEY},
    )


@pytest.fixture
def headers():
    return {
        "X-DIAL-APPLICATION-PROPERTIES": json.dumps(
            {"key1": "value1", "key2": "value2"}
        ),
    }


@pytest.fixture
def headers_without_app_properties_and_app_id():
    return {}


@pytest.fixture
def invalid_headers():
    return {
        "X-DIAL-APPLICATION-PROPERTIES": "invalid header",
    }


@pytest.fixture
def headers_with_app_id_only():
    return {
        "X-DIAL-APPLICATION-ID": X_APPLICATION_ID,
    }


parametrize_data = [
    (
        "chat/completions",
        "POST",
        {"messages": [{"role": "user", "content": "Hello"}]},
    ),
    ("configuration", "GET", None),
    ("rate", "POST", {"responseId": "123", "rate": False}),
    ("tokenize", "POST", {"inputs": []}),
    ("truncate_prompt", "POST", {"inputs": []}),
]


@pytest.mark.parametrize("endpoint, method, request_body", parametrize_data)
def test_valid_request(
    endpoint: str,
    method: str,
    request_body: Any,
    client: TestClient,
    headers: dict,
):
    response = client.request(
        url=endpoint,
        headers=headers,
        json=request_body,
        method=method,
    )
    assert response.status_code == 200


@pytest.mark.parametrize("endpoint, method, request_body", parametrize_data)
def test_request_without_app_props_and_id_headers(
    endpoint: str,
    method: str,
    request_body: Any,
    client: TestClient,
    headers_without_app_properties_and_app_id: dict,
):
    response = client.request(
        url=endpoint,
        headers=headers_without_app_properties_and_app_id,
        json=request_body,
        method=method,
    )
    response_data = response.json()
    assert response_data["error"]["type"] == "invalid_request_error"
    assert (
        response_data["error"]["message"]
        == "The X-DIAL-APPLICATION-ID header isn't set"
    )
    assert response.status_code == 400


@pytest.mark.parametrize("endpoint, method, request_body", parametrize_data)
def test_request_app_properties_from_core(
    endpoint: str,
    method: str,
    request_body: Any,
    client: TestClient,
    headers_with_app_id_only: dict,
    mock_app_props,
):
    response = client.request(
        url=endpoint,
        headers=headers_with_app_id_only,
        json=request_body,
        method=method,
    )
    assert response.status_code == 200


@pytest.mark.parametrize("endpoint, method, request_body", parametrize_data)
def test_invalid_application_properties_headers(
    endpoint: str,
    method: str,
    request_body: Any,
    client: TestClient,
    invalid_headers: dict,
):
    response = client.request(
        url=endpoint,
        headers=invalid_headers,
        json=request_body,
        method=method,
    )
    response_data = response.json()
    assert response_data["error"]["type"] == "invalid_request_error"
    assert response.status_code == 400


@pytest.mark.parametrize("endpoint, method, request_body", parametrize_data)
def test_core_request_error(
    endpoint: str,
    method: str,
    request_body: Any,
    client: TestClient,
    headers_with_app_id_only: dict,
    mock_app_props_error,
):
    response = client.request(
        url=endpoint,
        headers=headers_with_app_id_only,
        json=request_body,
        method=method,
    )
    response_data = response.json()
    assert response_data["error"]["type"] == "internal_server_error"
    assert response.status_code == 500


@pytest.mark.parametrize("endpoint, method, request_body", parametrize_data)
def test_request_dial_url_not_set(
    endpoint: str,
    method: str,
    request_body: Any,
    client_without_base_url: TestClient,
    headers_with_app_id_only: dict,
):
    response = client_without_base_url.request(
        url=endpoint,
        headers=headers_with_app_id_only,
        json=request_body,
        method=method,
    )
    response_data = response.json()
    assert response_data["error"]["type"] == "internal_server_error"
    assert response.status_code == 500
    assert (
        response_data["error"]["message"]
        == "DIALApp dial_url should be set to perform request_dial_application_properties invocation"
    )


async def test_import_error_handling():
    with patch.dict("sys.modules", {"httpx": None}):
        testable_class = FromRequestDeploymentMixin(
            headers=MutableHeaders({"X-DIAL-APPLICATION-ID": X_APPLICATION_ID}),
            base_url="https://test.com",
            api_key_secret=SecretStr("123"),
            jwt_secret=None,
            api_version=None,
            deployment_id=StrictStr("123"),
            original_request=MagicMock(fastapi.Request),
            dial_application_id="123",
        )
        with pytest.raises(InternalServerError) as exc_info:
            await testable_class.request_dial_application_properties()

        assert (
            str(exc_info.value)
            == "Missing httpx dependencies. Install the package with the extras: aidial-sdk[httpx]"
        )


async def test_base_url_required_if_need_to_get_application_properties_from_core():
    testable_class = FromRequestDeploymentMixin(
        headers=MutableHeaders({"X-DIAL-APPLICATION-ID": X_APPLICATION_ID}),
        api_key_secret=SecretStr("123"),
        jwt_secret=None,
        api_version=None,
        deployment_id=StrictStr("123"),
        original_request=MagicMock(fastapi.Request),
        dial_application_id="123",
    )
    with pytest.raises(HTTPException) as exc_info:
        await testable_class.request_dial_application_properties()

    assert exc_info.value.status_code == 500
    assert exc_info.value.type == "internal_server_error"
    assert (
        exc_info.value.message
        == "DIALApp dial_url should be set to perform request_dial_application_properties invocation"
    )


async def test_return_unreliable_dial_application_properties_from_headers_on_request_to_core():
    testable_class = FromRequestDeploymentMixin(
        api_key_secret=SecretStr("123"),
        jwt_secret=None,
        api_version=None,
        deployment_id=StrictStr("123"),
        headers=MutableHeaders(
            {
                "X-DIAL-APPLICATION-PROPERTIES": json.dumps(
                    {"key1": "value1", "key2": "value2"}
                )
            }
        ),
        dial_application_id="123",
        unreliable_dial_application_properties={
            "key1": "value1",
            "key2": "value2",
        },
        base_url="https://test.com",
        original_request=MagicMock(fastapi.Request),
    )
    application_properties = (
        await testable_class.request_dial_application_properties()
    )
    assert application_properties == {"key1": "value1", "key2": "value2"}
