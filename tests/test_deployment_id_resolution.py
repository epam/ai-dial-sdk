from typing import Any

import pytest
from starlette.testclient import TestClient

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion import ChatCompletion, Request, Response
from aidial_sdk.deployment._headers import (
    DIAL_DEPLOYMENT_ID,
    DIAL_OVERRIDE_NAME,
)
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
from aidial_sdk.embeddings import Embeddings
from aidial_sdk.embeddings import Request as EmbeddingsRequest
from aidial_sdk.embeddings import Response as EmbeddingsResponse
from aidial_sdk.embeddings import Usage as EmbeddingsUsage

_API_KEY = "test-api-key"

_DEPLOYMENT_NAME = "test-app-name"
_OVERRIDE_NAME = "override-name"
_HEADER_DEPLOYMENT_ID = "header-deployment-id"

_DEPLOYMENTS_PATH = f"/openai/deployments/{_DEPLOYMENT_NAME}"
_V1_PATH = "/openai/v1"


class _DeploymentIdRecorder(ChatCompletion, Embeddings):
    def __init__(self) -> None:
        self.deployment_ids: list[str] = []

    def _record(self, request: FromRequestDeploymentMixin) -> None:
        self.deployment_ids.append(request.deployment_id)

    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        self._record(request)
        with response.create_single_choice():
            pass

    async def rate_response(self, request: RateRequest) -> None:
        self._record(request)

    async def tokenize(self, request: TokenizeRequest) -> TokenizeResponse:
        self._record(request)
        return TokenizeResponse(outputs=[])

    async def truncate_prompt(
        self, request: TruncatePromptRequest
    ) -> TruncatePromptResponse:
        self._record(request)
        return TruncatePromptResponse(outputs=[])

    async def configuration(
        self, request: ConfigurationRequest
    ) -> ConfigurationResponse:
        self._record(request)
        return ConfigurationResponse()

    async def embeddings(
        self, request: EmbeddingsRequest
    ) -> EmbeddingsResponse:
        self._record(request)
        return EmbeddingsResponse(
            data=[],
            model="dummy",
            usage=EmbeddingsUsage(prompt_tokens=1, total_tokens=1),
        )


# (method, endpoint, request body)
_ENDPOINTS: list[tuple[str, str, Any]] = [
    (
        "POST",
        "chat/completions",
        {
            "model": "request-model",
            "messages": [{"role": "user", "content": "hi"}],
        },
    ),
    ("POST", "rate", {"responseId": "123", "rate": False}),
    ("POST", "tokenize", {"inputs": []}),
    ("POST", "truncate_prompt", {"inputs": []}),
    ("GET", "configuration", None),
    ("POST", "embeddings", {"input": []}),
]

_endpoints = pytest.mark.parametrize(
    "method, endpoint, body", _ENDPOINTS, ids=[e[0] for e in _ENDPOINTS]
)

# (base path, extra headers, expected deployment_id)
_CONDITIONS: list[tuple[str, dict[str, str], str]] = [
    (_DEPLOYMENTS_PATH, {}, _DEPLOYMENT_NAME),
    (
        _DEPLOYMENTS_PATH,
        {DIAL_DEPLOYMENT_ID: _HEADER_DEPLOYMENT_ID},
        _DEPLOYMENT_NAME,
    ),
    (_DEPLOYMENTS_PATH, {DIAL_OVERRIDE_NAME: _OVERRIDE_NAME}, _OVERRIDE_NAME),
    (
        _DEPLOYMENTS_PATH,
        {
            DIAL_DEPLOYMENT_ID: _HEADER_DEPLOYMENT_ID,
            DIAL_OVERRIDE_NAME: _OVERRIDE_NAME,
        },
        _OVERRIDE_NAME,
    ),
    (
        _V1_PATH,
        {DIAL_DEPLOYMENT_ID: _HEADER_DEPLOYMENT_ID},
        _HEADER_DEPLOYMENT_ID,
    ),
    (_V1_PATH, {DIAL_OVERRIDE_NAME: _OVERRIDE_NAME}, _OVERRIDE_NAME),
    (
        _V1_PATH,
        {
            DIAL_DEPLOYMENT_ID: _HEADER_DEPLOYMENT_ID,
            DIAL_OVERRIDE_NAME: _OVERRIDE_NAME,
        },
        _OVERRIDE_NAME,
    ),
]

_conditions = pytest.mark.parametrize(
    "base_path, headers, expected",
    _CONDITIONS,
    ids=[
        "path",
        "path+deployment-id-header",
        "path+override-name-header",
        "path+both-headers",
        "v1+deployment-id-header",
        "v1+override-name-header",
        "v1+both-headers",
    ],
)


def _call(
    base_path: str,
    endpoint: str,
    method: str,
    body: Any,
    headers: dict[str, str],
):
    impl = _DeploymentIdRecorder()

    # the v1 endpoints dispatch by the resolved deployment id,
    # so every id the tests may resolve to has to be registered
    app = DIALApp()
    for name in (_DEPLOYMENT_NAME, _OVERRIDE_NAME, _HEADER_DEPLOYMENT_ID):
        app.add_chat_completion(name, impl).add_embeddings(name, impl)

    client = TestClient(app, headers={"Api-Key": _API_KEY})
    response = client.request(
        method, f"{base_path}/{endpoint}", json=body, headers=headers
    )
    return response, impl.deployment_ids


@_endpoints
@_conditions
def test_deployment_id(
    base_path: str,
    headers: dict[str, str],
    expected: str,
    endpoint: str,
    method: str,
    body: Any,
):
    response, deployment_ids = _call(base_path, endpoint, method, body, headers)
    assert response.status_code == 200
    assert deployment_ids == [expected]


@_endpoints
def test_deployment_id_missing(endpoint: str, method: str, body: Any):
    """The v1 endpoints have no deployment name in the path, so
    the deployment id must come from the headers."""

    response, deployment_ids = _call(_V1_PATH, endpoint, method, body, {})

    assert response.status_code == 500
    assert response.json()["error"]["message"] == (
        f"The request headers are missing {DIAL_DEPLOYMENT_ID} header."
    )
    assert deployment_ids == []


class _DeploymentNameEcho(ChatCompletion):
    """Replies with the deployment id of the request it received."""

    def __init__(self, name: str) -> None:
        self.name = name

    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        with response.create_single_choice() as choice:
            choice.append_content(f"{self.name}:{request.deployment_id}")


@pytest.mark.parametrize("header", [DIAL_OVERRIDE_NAME, DIAL_DEPLOYMENT_ID])
@pytest.mark.parametrize("deployment", ["app-one", "app-two"])
def test_v1_routing_between_deployments(deployment: str, header: str):
    """The v1 endpoints are shared by all the deployments of a single
    DIALApp, so they must be routed by the resolved deployment id."""

    app = (
        DIALApp()
        .add_chat_completion("app-one", _DeploymentNameEcho("app-one"))
        .add_chat_completion("app-two", _DeploymentNameEcho("app-two"))
    )
    client = TestClient(app, headers={"Api-Key": _API_KEY})

    response = client.post(
        "/openai/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers={header: deployment},
    )

    assert response.status_code == 200
    assert (
        response.json()["choices"][0]["message"]["content"]
        == f"{deployment}:{deployment}"
    )


@pytest.mark.parametrize(
    "endpoint, deployment",
    [
        ("chat/completions", "app-unknown"),
        # app-two doesn't implement tokenize, so its v1 route is
        # registered by app-one only
        ("tokenize", "app-two"),
    ],
)
def test_v1_unknown_deployment(endpoint: str, deployment: str):
    class _Tokenizer(_DeploymentNameEcho):
        async def tokenize(self, request: TokenizeRequest) -> TokenizeResponse:
            return TokenizeResponse(outputs=[])

    app = (
        DIALApp()
        .add_chat_completion("app-one", _Tokenizer("app-one"))
        .add_chat_completion("app-two", _DeploymentNameEcho("app-two"))
    )
    client = TestClient(app, headers={"Api-Key": _API_KEY})

    response = client.post(
        f"/openai/v1/{endpoint}",
        json={"messages": [], "inputs": []},
        headers={DIAL_DEPLOYMENT_ID: deployment},
    )

    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "DeploymentNotFound",
        "message": f"The deployment '{deployment}' doesn't provide the '{endpoint}' endpoint",
        "type": "runtime_error",
    }
