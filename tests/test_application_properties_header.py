import pytest
from starlette.testclient import TestClient

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion import ChatCompletion, Request, Response
from aidial_sdk.deployment.configuration import ConfigurationRequest, ConfigurationResponse
import json

from aidial_sdk.deployment.rate import RateRequest
from aidial_sdk.deployment.tokenize import TokenizeRequest, TokenizeResponse
from aidial_sdk.deployment.truncate_prompt import TruncatePromptRequest, TruncatePromptResponse


class TestApp(ChatCompletion):
    async def chat_completion(self, request: Request, response: Response):
        assert request.application_properties == {"key1": "value1", "key2": "value2"}
        with response.create_choice() as choice:
            choice.append_content("Hello")

    async def configuration(self, request: ConfigurationRequest):
        assert request.application_properties == {"key1": "value1", "key2": "value2"}
        return ConfigurationResponse()

    async def rate_response(self, request: RateRequest):
        assert request.application_properties == {"key1": "value1", "key2": "value2"}

    async def tokenize(self, request: TokenizeRequest):
        assert request.application_properties == {"key1": "value1", "key2": "value2"}
        return TokenizeResponse(outputs=[])

    async def truncate_prompt(self, request: TruncatePromptRequest):
        assert request.application_properties == {"key1": "value1", "key2": "value2"}
        return TruncatePromptResponse(outputs=[])

deployment_name = "test-app"
API_KEY = "test-api-key"

@pytest.fixture
def client():
    app = DIALApp().add_chat_completion(deployment_name, TestApp())
    return TestClient(app)

@pytest.fixture
def headers():
    return {
        "Api-Key": API_KEY,
        "Authorization": "Bearer test-jwt",
        "X-APPLICATION-PROPERTIES": json.dumps({"key1": "value1", "key2": "value2"})
    }

@pytest.fixture
def body():
    return {
        "messages": [
            {"role": "user", "content": "Hello"}
        ]
    }

def test_chat_completion_request(client: TestClient, headers: dict, body: dict):
    response = client.post(f"/openai/deployments/{deployment_name}/chat/completions", headers=headers, json=body)
    assert response.status_code == 200

def test_configuration_request(client: TestClient, headers: dict, body: dict):
    response = client.get(f"/openai/deployments/{deployment_name}/configuration", headers=headers)
    assert response.status_code == 200

def test_rate_response_request(client: TestClient, headers: dict, body: dict):
    response = client.post(f"/openai/deployments/{deployment_name}/rate", headers=headers, json={"responseId": "123", "rate": False})
    assert response.status_code == 200

def test_tokenize_request(client: TestClient, headers: dict, body: dict):
    response = client.post(f"/openai/deployments/{deployment_name}/tokenize", headers=headers, json={"inputs": []})
    assert response.status_code == 200

def test_truncate_prompt_request(client: TestClient, headers: dict, body: dict):
    response = client.post(f"/openai/deployments/{deployment_name}/truncate_prompt", headers=headers, json={"inputs": []})
    assert response.status_code == 200



