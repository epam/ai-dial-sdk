from typing import Dict, Union

from fastapi import FastAPI
from starlette.testclient import TestClient

from tests.utils.errors import Error


class TestCase:
    __test__ = False

    app: FastAPI

    deployment: str
    endpoint: str

    request_body: dict
    request_headers: Dict[str, str]
    response: Union[Error, dict, None]

    def __init__(
        self,
        app: FastAPI,
        deployment: str,
        endpoint: str,
        request_body: dict,
        response: Union[Error, dict, None],
        request_headers: Dict[str, str] = {},
    ):
        self.app = app
        self.deployment = deployment
        self.endpoint = endpoint
        self.request_body = request_body
        self.response = response
        self.request_headers = request_headers


def run_endpoint_test(testcase: TestCase):

    test_app = TestClient(testcase.app)

    actual_response = test_app.post(
        f"/openai/deployments/{testcase.deployment}/{testcase.endpoint}",
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

    assert actual_response_body == expected_response_body
    assert actual_response.status_code == expected_response_code
