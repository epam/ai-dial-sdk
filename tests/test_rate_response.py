from typing import List

import pytest
from starlette.testclient import TestClient

from aidial_sdk import DIALApp
from tests.applications.single_choice_application import SingleChoiceApplication
from tests.utils.endpoint_test import TestCase, run_endpoint_test_case
from tests.utils.errors import extra_fields_error

RATE_REQUEST_OK1 = {}
RATE_REQUEST_OK2 = {"responseId": "0", "rate": True}
RATE_REQUEST_FAIL = {"foo": "bar"}


app = SingleChoiceApplication()

testcases: List[TestCase] = [
    TestCase(app, "rate", RATE_REQUEST_OK2, None),
    TestCase(app, "rate", RATE_REQUEST_OK1, None),
    TestCase(app, "rate", RATE_REQUEST_FAIL, extra_fields_error("foo")),
]


@pytest.mark.parametrize("testcase", testcases)
def test_rate_endpoint(testcase: TestCase):
    run_endpoint_test_case(testcase)


def test_rate_response():
    dial_app = DIALApp()
    dial_app.add_chat_completion("test_app", SingleChoiceApplication())

    test_app = TestClient(dial_app)

    response = test_app.post(
        "/openai/deployments/test_app/rate",
        json={
            "responseId": "123",
            "rate": True,
        },
    )

    assert response.status_code == 200
