from typing import Dict, Union

from starlette.testclient import TestClient

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion.base import ChatCompletion
from aidial_sdk.embeddings.base import Embeddings
from tests.utils.errors import Error


class TestCase:
    __test__ = False

    app: Union[ChatCompletion, Embeddings]
    endpoint: str

    request_body: dict
    request_headers: Dict[str, str]

    response: Union[Error, dict, None]

    def __init__(
        self,
        app: Union[ChatCompletion, Embeddings],
        endpoint: str,
        request_body: dict,
        response: Union[Error, dict, None],
        request_headers: Dict[str, str] = {},
    ):
        self.app = app
        self.endpoint = endpoint
        self.request_body = request_body
        self.request_headers = request_headers
        self.response = response


def run_endpoint_test(testcase: TestCase):
    dial_app = DIALApp()

    if isinstance(testcase.app, Embeddings):
        dial_app.add_embeddings("test_app", testcase.app)
    else:
        dial_app.add_chat_completion("test_app", testcase.app)

    test_app = TestClient(dial_app)

    actual_response = test_app.post(
        f"/openai/deployments/test_app/{testcase.endpoint}",
        json=testcase.request_body,
        headers={"Api-Key": "TEST_API_KEY", **testcase.request_headers},
    )

    if actual_response.text == "":
        actual_response_body = None
    else:
        actual_response_body = actual_response.json()

    expected_response = testcase.response
    if isinstance(expected_response, Error):
        expected_response_code = expected_response.code
        expected_response_body = expected_response.error
    else:
        expected_response_code = 200
        expected_response_body = expected_response

    assert actual_response.status_code == expected_response_code
    assert actual_response_body == expected_response_body
