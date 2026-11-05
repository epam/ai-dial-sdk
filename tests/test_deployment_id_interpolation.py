import pytest
from starlette.testclient import TestClient

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion import ChatCompletion
from aidial_sdk.chat_completion import Request as ChatRequest
from aidial_sdk.chat_completion import Response as ChatResponse
from aidial_sdk.deployment._headers import DIAL_DEPLOYMENT_ID
from aidial_sdk.embeddings import Embeddings
from aidial_sdk.embeddings import Request as EmbeddingRequest
from aidial_sdk.embeddings import Response as EmbeddingResponse
from aidial_sdk.embeddings import Usage as EmbeddingUsage
from tests.utils.endpoint_test import TestCase, run_endpoint_test


class _DeploymentIdChecker(ChatCompletion, Embeddings):
    expected_deployment_id: str
    expected_idx_value: str | int

    def __init__(
        self, expected_deployment_id: str, expected_idx_value: str | int
    ):
        self.expected_deployment_id = expected_deployment_id
        self.expected_idx_value = expected_idx_value

    async def chat_completion(
        self, request: ChatRequest, response: ChatResponse
    ) -> None:
        assert request.deployment_id == self.expected_deployment_id, (
            f"Expected deployment_id='{self.expected_deployment_id}', got '{request.deployment_id}'"
        )

        assert "idx" in request.original_request.path_params
        assert (
            request.original_request.path_params["idx"]
            == self.expected_idx_value
        )

        with response.create_single_choice() as choice:
            choice.append_content("test")

    async def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        assert request.deployment_id == self.expected_deployment_id, (
            f"Expected deployment_id='{self.expected_deployment_id}', got '{request.deployment_id}'"
        )

        assert "idx" in request.original_request.path_params
        assert (
            request.original_request.path_params["idx"]
            == self.expected_idx_value
        )

        return EmbeddingResponse(
            data=[],
            model="dummy",
            usage=EmbeddingUsage(prompt_tokens=1, total_tokens=1),
        )


_CHAT_APP = DIALApp().add_chat_completion(
    "app-{idx}", _DeploymentIdChecker("app-123", "123")
)

_CHAT_APP_WITH_PARSER = DIALApp().add_chat_completion(
    "app-{idx:int}", _DeploymentIdChecker("app-123", 123)
)

_EMBEDDINGS_APP = DIALApp().add_embeddings(
    "app-{idx}", _DeploymentIdChecker("app-456", "456")
)

_EMBEDDINGS_APP_WITH_PARSER = DIALApp().add_embeddings(
    "app-{idx:int}", _DeploymentIdChecker("app-456", 456)
)


_TESTCASES: list[TestCase] = [
    TestCase(_CHAT_APP, "app-123", "chat/completions", {"messages": []}, None),
    TestCase(
        _CHAT_APP_WITH_PARSER,
        "app-123",
        "chat/completions",
        {"messages": []},
        None,
    ),
    TestCase(_EMBEDDINGS_APP, "app-456", "embeddings", {"input": []}, None),
    TestCase(
        _EMBEDDINGS_APP_WITH_PARSER,
        "app-456",
        "embeddings",
        {"input": []},
        None,
    ),
]


@pytest.mark.parametrize("testcase", _TESTCASES)
def test_deployment_id_interpolation(testcase: TestCase):
    run_endpoint_test(testcase)


# The /openai/v1 endpoints take the deployment id from the headers instead
# of the path, so the templates are matched against that id.
_V1_TESTCASES: list[tuple[DIALApp, str, str, dict]] = [
    (_CHAT_APP, "app-123", "chat/completions", {"messages": []}),
    (_CHAT_APP_WITH_PARSER, "app-123", "chat/completions", {"messages": []}),
    (_EMBEDDINGS_APP, "app-456", "embeddings", {"input": []}),
    (_EMBEDDINGS_APP_WITH_PARSER, "app-456", "embeddings", {"input": []}),
]


@pytest.mark.parametrize("app, deployment, endpoint, body", _V1_TESTCASES)
def test_v1_deployment_id_interpolation(
    app: DIALApp, deployment: str, endpoint: str, body: dict
):
    response = TestClient(app).post(
        f"/openai/v1/{endpoint}",
        json=body,
        headers={"Api-Key": "TEST_API_KEY", DIAL_DEPLOYMENT_ID: deployment},
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    "deployment", ["other-123", "app-", "app-123/sub", "app-abc"]
)
def test_v1_deployment_id_not_matching_template(deployment: str):
    """A template is not a catch-all: ids it doesn't match are still 404."""

    response = TestClient(_CHAT_APP_WITH_PARSER).post(
        "/openai/v1/chat/completions",
        json={"messages": []},
        headers={"Api-Key": "TEST_API_KEY", DIAL_DEPLOYMENT_ID: deployment},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DeploymentNotFound"
