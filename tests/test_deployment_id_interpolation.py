import pytest

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion import ChatCompletion
from aidial_sdk.chat_completion import Request as ChatRequest
from aidial_sdk.chat_completion import Response as ChatResponse
from aidial_sdk.embeddings import Embeddings
from aidial_sdk.embeddings import Request as EmbeddingRequest
from aidial_sdk.embeddings import Response as EmbeddingResponse
from aidial_sdk.embeddings import Usage as EmbeddingUsage
from tests.utils.endpoint_test import TestCase, run_endpoint_test


class _DeploymentIdChecker(ChatCompletion, Embeddings):
    expected_deployment_id: str

    def __init__(self, expected_deployment_id: str):
        self.expected_deployment_id = expected_deployment_id

    async def chat_completion(
        self, request: ChatRequest, response: ChatResponse
    ) -> None:
        assert (
            request.deployment_id == self.expected_deployment_id
        ), f"Expected deployment_id='{self.expected_deployment_id}', got '{request.deployment_id}'"

        assert "idx" in request.original_request.path_params
        assert request.original_request.path_params["idx"] == "123"

        with response.create_single_choice() as choice:
            choice.append_content("test")

    async def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        assert (
            request.deployment_id == self.expected_deployment_id
        ), f"Expected deployment_id='{self.expected_deployment_id}', got '{request.deployment_id}'"

        assert "idx" in request.original_request.path_params
        assert request.original_request.path_params["idx"] == "456"

        return EmbeddingResponse(
            data=[],
            model="dummy",
            usage=EmbeddingUsage(prompt_tokens=1, total_tokens=1),
        )


_CHAT_APP = DIALApp().add_chat_completion(
    "app-{idx}", _DeploymentIdChecker("app-123")
)

_EMBEDDINGS_APP = DIALApp().add_embeddings(
    "app-{idx}", _DeploymentIdChecker("app-456")
)


_TESTCASES: list[TestCase] = [
    TestCase(_CHAT_APP, "app-123", "chat/completions", {"messages": []}, None),
    TestCase(_EMBEDDINGS_APP, "app-456", "embeddings", {"input": []}, None),
]


@pytest.mark.parametrize("testcase", _TESTCASES)
def test_deployment_id_interpolation(testcase: TestCase):
    run_endpoint_test(testcase)
