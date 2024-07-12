from typing import Union

from fastapi import FastAPI
from starlette.testclient import TestClient

from tests.utils.errors import Error


class TestCase:
    __test__ = False

    app: FastAPI

    deployment: str
    endpoint: str

    request: dict
    response: Union[Error, dict, None]

    def __init__(
        self,
        app: FastAPI,
        deployment: str,
        endpoint: str,
        request: dict,
        response: Union[Error, dict, None],
    ):
        self.app = app
        self.deployment = deployment
        self.endpoint = endpoint
        self.request = request
        self.response = response


def run_endpoint_test(testcase: TestCase):

    test_app = TestClient(testcase.app)

    actual_response = test_app.post(
        f"/openai/deployments/{testcase.deployment}/{testcase.endpoint}",
        json=testcase.request,
        headers={"Api-Key": "TEST_API_KEY"},
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
