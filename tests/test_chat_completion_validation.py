from typing import List

import pytest

from aidial_sdk import DIALApp
from aidial_sdk._pydantic._compat import PYDANTIC_V2
from aidial_sdk.chat_completion import ChatCompletion, Request, Response
from tests.utils.endpoint_test import TestCase, run_endpoint_test
from tests.utils.errors import internal_server_error, invalid_request_error


class App(ChatCompletion):
    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        with response.create_single_choice() as choice:
            choice.add_attachment(data="xxx", url="yyy")


VALID_REQUEST = {"messages": [{"role": "user", "content": "test"}]}
INVALID_ATTACHMENT_BOTH = {
    "messages": [
        {
            "role": "user",
            "content": "test",
            "custom_content": {"attachments": [{"data": "xxx", "url": "yyy"}]},
        }
    ]
}
INVALID_ATTACHMENT_NEITHER = {
    "messages": [
        {
            "role": "user",
            "content": "test",
            "custom_content": {"attachments": [{"title": "title"}]},
        }
    ]
}


deployment = "test-app"

noop = DIALApp().add_chat_completion(deployment, App())


testcases: List[TestCase] = [
    TestCase(
        noop,
        deployment,
        "chat/completions",
        VALID_REQUEST,
        internal_server_error("Error during processing the request"),
    ),
    TestCase(
        noop,
        deployment,
        "chat/completions",
        INVALID_ATTACHMENT_BOTH,
        invalid_request_error(
            "messages.0.custom_content.attachments.0"
            + ("" if PYDANTIC_V2 else ".__root__"),
            ("Value error, " if PYDANTIC_V2 else "")
            + "Attachment must have either 'data' or 'url', but it has both",
        ),
    ),
    TestCase(
        noop,
        deployment,
        "chat/completions",
        INVALID_ATTACHMENT_NEITHER,
        invalid_request_error(
            "messages.0.custom_content.attachments.0"
            + ("" if PYDANTIC_V2 else ".__root__"),
            ("Value error, " if PYDANTIC_V2 else "")
            + "Attachment must have either 'data' or 'url', but it's missing both",
        ),
    ),
]


@pytest.mark.parametrize("testcase", testcases)
def test_chat_completion_validation(testcase: TestCase):
    run_endpoint_test(testcase)
