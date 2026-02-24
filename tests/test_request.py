import pytest

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion import ChatCompletion
from aidial_sdk.chat_completion import Request as ChatRequest
from aidial_sdk.deployment.from_request_mixin import FromRequestDeploymentMixin
from aidial_sdk.embeddings import Embeddings
from aidial_sdk.embeddings import Request as EmbeddingRequest
from aidial_sdk.embeddings import Response as EmbeddingResponse
from aidial_sdk.embeddings import Usage as EmbeddingUsage
from tests.utils.endpoint_test import TestCase, run_endpoint_test


class _TestApp(ChatCompletion, Embeddings):
    headers: list[str]

    @staticmethod
    def _header_variations(header: str):
        yield header
        yield header.lower()
        yield header.upper()
        yield "".join(
            c.upper() if i % 2 else c.lower() for (i, c) in enumerate(header)
        )

    def __init__(self, headers: list[str]):
        self.headers = headers

    def _check_headers(self, request: FromRequestDeploymentMixin):
        for header in self.headers:
            for h in self._header_variations(header):
                assert h in request.headers

    async def chat_completion(self, request: ChatRequest, response) -> None:
        self._check_headers(request)

        with response.create_single_choice() as choice:
            choice.append_content("test")

    async def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        self._check_headers(request)

        return EmbeddingResponse(
            data=[],
            model="dummy",
            usage=EmbeddingUsage(prompt_tokens=1, total_tokens=1),
        )


_APP = (
    DIALApp()
    .add_chat_completion("{deployment_id}", _TestApp(["x-test-header"]))
    .add_embeddings("{deployment_id}", _TestApp(["x-test-header"]))
)

_HEADERS = {"x-test-header": "test-header-value"}

_TESTCASES: list[TestCase] = [
    TestCase(
        _APP, "test-app", "chat/completions", {"messages": []}, None, _HEADERS
    ),
    TestCase(_APP, "test-app", "embeddings", {"input": []}, None, _HEADERS),
]


@pytest.mark.parametrize("testcase", _TESTCASES)
def test_request_headers(testcase: TestCase):
    run_endpoint_test(testcase)
