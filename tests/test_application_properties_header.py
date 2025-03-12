import json
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest
from pydantic.v1 import StrictStr
from starlette.datastructures import MutableHeaders
from starlette.testclient import TestClient
from aidial_sdk.pydantic_v1 import SecretStr

from aidial_sdk import DIALApp, HTTPException
from aidial_sdk.chat_completion import ChatCompletion, Request, Response
from aidial_sdk.deployment.configuration import (
    ConfigurationRequest,
    ConfigurationResponse,
)
from aidial_sdk.deployment.rate import RateRequest
from aidial_sdk.deployment.schema_rich_applications_mixin import (
    SchemaRichApplicationsMixin,
)
from aidial_sdk.deployment.tokenize import TokenizeRequest, TokenizeResponse
from aidial_sdk.deployment.truncate_prompt import (
    TruncatePromptRequest,
    TruncatePromptResponse,
)


class TestApp(ChatCompletion):
    async def chat_completion(self, request: Request, response: Response):
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
        with response.create_choice() as choice:
            choice.append_content("Hello")

    async def configuration(self, request: ConfigurationRequest):
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
        return ConfigurationResponse()

    async def rate_response(self, request: RateRequest):
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

    async def tokenize(self, request: TokenizeRequest):
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
        return TokenizeResponse(outputs=[])

    async def truncate_prompt(self, request: TruncatePromptRequest):
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
        return TruncatePromptResponse(outputs=[])


deployment_name = "test-app"
API_KEY = "test-api-key"


@pytest.fixture
def client():
    with patch("httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "application_properties": {"key1": "value1", "key2": "value2"}
        }
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.request.return_value = mock_response
        MockClient.return_value = mock_client
        app = DIALApp(dial_url="https://test.com").add_chat_completion(
            deployment_name, TestApp()
        )
        yield TestClient(app)


@pytest.fixture
def client_without_base_url():
    with patch("httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "application_properties": {"key1": "value1", "key2": "value2"}
        }
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.request.return_value = mock_response
        MockClient.return_value = mock_client
        app = DIALApp().add_chat_completion(deployment_name, TestApp())
        yield TestClient(app)


@pytest.fixture
def client_mock_error_core_response():
    with patch("httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            message="Server error", request=MagicMock(), response=mock_response
        )
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.request.return_value = mock_response
        MockClient.return_value = mock_client
        app = DIALApp(dial_url="https://test.com").add_chat_completion(
            deployment_name, TestApp()
        )
        yield TestClient(app)


@pytest.fixture
def headers():
    return {
        "Api-Key": API_KEY,
        "Authorization": "Bearer test-jwt",
        "X-DIAL-APPLICATION-PROPERTIES": json.dumps(
            {"key1": "value1", "key2": "value2"}
        ),
    }


@pytest.fixture
def headers_without_app_properties_and_app_id():
    return {"Api-Key": API_KEY, "Authorization": "Bearer test-jwt"}


@pytest.fixture
def invalid_headers():
    return {
        "Api-Key": API_KEY,
        "Authorization": "Bearer test-jwt",
        "X-DIAL-APPLICATION-PROPERTIES": "invalid header",
    }


@pytest.fixture
def headers_with_app_id_only():
    return {
        "Api-Key": API_KEY,
        "Authorization": "Bearer test-jwt",
        "X-DIAL-APPLICATION-ID": "112233",
    }


@pytest.fixture
def body():
    return {"messages": [{"role": "user", "content": "Hello"}]}


def test_chat_completion_request(client: TestClient, headers: dict, body: dict):
    response = client.post(
        f"/openai/deployments/{deployment_name}/chat/completions",
        headers=headers,
        json=body,
    )
    assert response.status_code == 200


def test_chat_completion_request_without_app_props_and_id_headers(
    client: TestClient,
    headers_without_app_properties_and_app_id: dict,
    body: dict,
):
    response = client.post(
        f"/openai/deployments/{deployment_name}/chat/completions",
        headers=headers_without_app_properties_and_app_id,
        json=body,
    )
    response_data = json.loads(response.content)
    assert response_data["error"]["type"] == "invalid_request_error"
    assert (
        response_data["error"]["message"]
        == "The X-DIAL-APPLICATION-ID header isn't set"
    )
    assert response.status_code == 400


def test_chat_completion_request_app_properties_from_core(
    client: TestClient, headers_with_app_id_only: dict, body: dict
):
    response = client.post(
        f"/openai/deployments/{deployment_name}/chat/completions",
        headers=headers_with_app_id_only,
        json=body,
    )
    assert response.status_code == 200


def test_chat_completion_invalid_application_properties_headers(
    client: TestClient, invalid_headers: dict, body: dict
):
    response = client.post(
        f"/openai/deployments/{deployment_name}/chat/completions",
        headers=invalid_headers,
        json=body,
    )
    response_data = json.loads(response.content)
    assert response_data["error"]["type"] == "invalid_request_error"
    assert response.status_code == 400


def test_chat_completion_core_request_error(
    client_mock_error_core_response: TestClient,
    headers_with_app_id_only: dict,
    body: dict,
):
    response = client_mock_error_core_response.post(
        f"/openai/deployments/{deployment_name}/chat/completions",
        headers=headers_with_app_id_only,
        json=body,
    )
    response_data = json.loads(response.content)
    assert response_data["error"]["type"] == "internal_request_error"
    assert response.status_code == 500


def test_chat_completion_request_dial_url_not_set(
    client_without_base_url: TestClient,
    headers_with_app_id_only: dict,
    body: dict,
):
    response = client_without_base_url.post(
        f"/openai/deployments/{deployment_name}/chat/completions",
        headers=headers_with_app_id_only,
        json=body,
    )
    response_data = json.loads(response.content)
    assert response_data["error"]["type"] == "dependency_error"
    assert response.status_code == 500
    assert (
        response_data["error"]["message"]
        == "Base url should be set to perform request_dial_application_properties invocation"
    )


def test_configuration_request_without_app_props_and_id_headers(
    client: TestClient, headers_without_app_properties_and_app_id: dict
):
    response = client.get(
        f"/openai/deployments/{deployment_name}/configuration",
        headers=headers_without_app_properties_and_app_id,
    )
    response_data = json.loads(response.content)
    assert response_data["error"]["type"] == "invalid_request_error"
    assert (
        response_data["error"]["message"]
        == "The X-DIAL-APPLICATION-ID header isn't set"
    )
    assert response.status_code == 400


def test_configuration_request(client: TestClient, headers: dict):
    response = client.get(
        f"/openai/deployments/{deployment_name}/configuration", headers=headers
    )
    assert response.status_code == 200


def test_configuration_request_app_properties_from_core(
    client: TestClient, headers_with_app_id_only: dict
):
    response = client.get(
        f"/openai/deployments/{deployment_name}/configuration",
        headers=headers_with_app_id_only,
    )
    assert response.status_code == 200


def test_configuration_request_invalid_application_properties_headers(
    client: TestClient, invalid_headers: dict
):
    response = client.get(
        f"/openai/deployments/{deployment_name}/configuration",
        headers=invalid_headers,
    )
    response_data = json.loads(response.content)
    assert response_data["error"]["type"] == "invalid_request_error"
    assert response.status_code == 400


def test_configuration_request_core_request_error(
    client_mock_error_core_response: TestClient, headers_with_app_id_only: dict
):
    response = client_mock_error_core_response.get(
        f"/openai/deployments/{deployment_name}/configuration",
        headers=headers_with_app_id_only,
    )
    response_data = json.loads(response.content)
    assert response_data["error"]["type"] == "internal_request_error"
    assert response.status_code == 500


def test_rate_response_request(client: TestClient, headers: dict):
    response = client.post(
        f"/openai/deployments/{deployment_name}/rate",
        headers=headers,
        json={"responseId": "123", "rate": False},
    )
    assert response.status_code == 200


def test_rate_response_request_without_app_props_and_id_headers(
    client: TestClient, headers_without_app_properties_and_app_id: dict
):
    response = client.post(
        f"/openai/deployments/{deployment_name}/rate",
        headers=headers_without_app_properties_and_app_id,
        json={"responseId": "123", "rate": False},
    )
    response_data = json.loads(response.content)
    assert response_data["error"]["type"] == "invalid_request_error"
    assert (
        response_data["error"]["message"]
        == "The X-DIAL-APPLICATION-ID header isn't set"
    )
    assert response.status_code == 400


def test_rate_response_request_invalid_application_properties_headers(
    client: TestClient, invalid_headers: dict
):
    response = client.post(
        f"/openai/deployments/{deployment_name}/rate",
        headers=invalid_headers,
        json={"responseId": "123", "rate": False},
    )
    response_data = json.loads(response.content)
    assert response_data["error"]["type"] == "invalid_request_error"
    assert response.status_code == 400


def test_rate_response_request_core_request_error(
    client_mock_error_core_response: TestClient, headers_with_app_id_only: dict
):
    response = client_mock_error_core_response.post(
        f"/openai/deployments/{deployment_name}/rate",
        headers=headers_with_app_id_only,
        json={"responseId": "123", "rate": False},
    )
    response_data = json.loads(response.content)
    assert response_data["error"]["type"] == "internal_request_error"
    assert response.status_code == 500


def test_tokenize_request(client: TestClient, headers: dict):
    response = client.post(
        f"/openai/deployments/{deployment_name}/tokenize",
        headers=headers,
        json={"inputs": []},
    )
    assert response.status_code == 200


def test_tokenize_request_without_app_props_and_id_headers(
    client: TestClient, headers_without_app_properties_and_app_id: dict
):
    response = client.post(
        f"/openai/deployments/{deployment_name}/tokenize",
        headers=headers_without_app_properties_and_app_id,
        json={"inputs": []},
    )
    response_data = json.loads(response.content)
    assert response_data["error"]["type"] == "invalid_request_error"
    assert (
        response_data["error"]["message"]
        == "The X-DIAL-APPLICATION-ID header isn't set"
    )
    assert response.status_code == 400


def test_tokenize_request__app_properties_from_core(
    client: TestClient, headers_with_app_id_only: dict
):
    response = client.post(
        f"/openai/deployments/{deployment_name}/tokenize",
        headers=headers_with_app_id_only,
        json={"inputs": []},
    )
    assert response.status_code == 200


def test_tokenize_request_invalid_application_properties_headers(
    client: TestClient, invalid_headers: dict
):
    response = client.post(
        f"/openai/deployments/{deployment_name}/tokenize",
        headers=invalid_headers,
        json={"inputs": []},
    )
    response_data = json.loads(response.content)
    assert response_data["error"]["type"] == "invalid_request_error"
    assert response.status_code == 400


def test_tokenize_request_core_request_error(
    client_mock_error_core_response: TestClient, headers_with_app_id_only: dict
):
    response = client_mock_error_core_response.post(
        f"/openai/deployments/{deployment_name}/tokenize",
        headers=headers_with_app_id_only,
        json={"inputs": []},
    )
    response_data = json.loads(response.content)
    assert response_data["error"]["type"] == "internal_request_error"
    assert response.status_code == 500


def test_truncate_prompt_request(client: TestClient, headers: dict):
    response = client.post(
        f"/openai/deployments/{deployment_name}/truncate_prompt",
        json={"inputs": []},
        headers=headers,
    )
    assert response.status_code == 200


def test_truncate_prompt_request_without_app_props_and_id_headers(
    client: TestClient, headers_without_app_properties_and_app_id: dict
):
    response = client.post(
        f"/openai/deployments/{deployment_name}/truncate_prompt",
        json={"inputs": []},
        headers=headers_without_app_properties_and_app_id,
    )
    response_data = json.loads(response.content)
    assert response_data["error"]["type"] == "invalid_request_error"
    assert (
        response_data["error"]["message"]
        == "The X-DIAL-APPLICATION-ID header isn't set"
    )
    assert response.status_code == 400


def test_truncate_prompt_request_app_properties_from_core(
    client: TestClient, headers_with_app_id_only: dict
):
    response = client.post(
        f"/openai/deployments/{deployment_name}/truncate_prompt",
        json={"inputs": []},
        headers=headers_with_app_id_only,
    )
    assert response.status_code == 200


def test_truncate_prompt_request_invalid_application_properties_headers(
    client: TestClient, invalid_headers: dict
):
    response = client.post(
        f"/openai/deployments/{deployment_name}/truncate_prompt",
        headers=invalid_headers,
        json={"inputs": []},
    )
    response_data = json.loads(response.content)
    assert response_data["error"]["type"] == "invalid_request_error"
    assert response.status_code == 400


def test_truncate_prompt_core_request_error(
    client_mock_error_core_response: TestClient, headers_with_app_id_only: dict
):
    response = client_mock_error_core_response.post(
        f"/openai/deployments/{deployment_name}/truncate_prompt",
        headers=headers_with_app_id_only,
        json={"inputs": []},
    )
    response_data = json.loads(response.content)
    assert response_data["error"]["type"] == "internal_request_error"
    assert response.status_code == 500


class TestSchemaRichApplicationsMixin(SchemaRichApplicationsMixin):
    pass


async def test_import_error_handling():
    with patch.dict("sys.modules", {"httpx": None}):
        testable_class = TestSchemaRichApplicationsMixin(
            headers=MutableHeaders({"X-DIAL-APPLICATION-ID": "123"}),
            base_url="https://test.com",
            api_key_secret=SecretStr("123"),
            jwt_secret=None,
            api_version=None,
            deployment_id=StrictStr("123"),
        )
        try:
            await testable_class.request_dial_application_properties()
        except HTTPException as exc_info:
            code = exc_info.status_code
            ex_type = exc_info.type
            message = exc_info.message

        assert code == 500
        assert ex_type == "dependency_error"
        assert (
            message
            == "Httpx is not installed. Please install it as extras dependency."
        )


async def test_base_url_required_if_need_to_get_application_properties_from_core():
    testable_class = TestSchemaRichApplicationsMixin(
        headers=MutableHeaders({"X-DIAL-APPLICATION-ID": "123"}),
        api_key_secret=SecretStr("123"),
        jwt_secret=None,
        api_version=None,
        deployment_id=StrictStr("123"),
    )
    code = 0
    ex_type = None
    message = None
    try:
        await testable_class.request_dial_application_properties()
    except HTTPException as exc_info:
        code = exc_info.status_code
        ex_type = exc_info.type
        message = exc_info.message

    assert code == 500
    assert ex_type == "dependency_error"
    assert (
        message
        == "Base url should be set to perform request_dial_application_properties invocation"
    )


async def test_return_unreliable_dial_application_properties_from_headers_on_reqeust_to_core():
    testable_class = TestSchemaRichApplicationsMixin(
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
    )
    application_properties = (
        await testable_class.request_dial_application_properties()
    )
    assert application_properties == {"key1": "value1", "key2": "value2"}
