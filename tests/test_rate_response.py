from typing import List

import pytest

from aidial_sdk import DIALApp
from tests.applications.noop import NoopApplication
from tests.utils.endpoint_test import TestCase, run_endpoint_test
from tests.utils.errors import extra_fields_error

RATE_REQUEST_OK1 = {}
RATE_REQUEST_OK2 = {"responseId": "123", "rate": True}
RATE_REQUEST_FAIL = {"foo": "bar"}


deployment = "test-app"
app = DIALApp().add_chat_completion(deployment, NoopApplication())


testcases: List[TestCase] = [
    TestCase(app, deployment, "rate", RATE_REQUEST_OK2, None),
    TestCase(app, deployment, "rate", RATE_REQUEST_OK1, None),
    TestCase(
        app, deployment, "rate", RATE_REQUEST_FAIL, extra_fields_error("foo")
    ),
]


@pytest.mark.parametrize("testcase", testcases)
def test_rate_endpoint(testcase: TestCase):
    run_endpoint_test(testcase)
