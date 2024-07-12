from typing import List, Optional

import pytest

from aidial_sdk import DIALApp
from tests.applications.echo import EchoApplication
from tests.applications.noop import NoopApplication
from tests.utils.endpoint_test import TestCase, run_endpoint_test
from tests.utils.errors import route_not_found_error

CHAT_COMPLETION_REQUEST = {
    "messages": [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "ping"},
        {"role": "assistant", "content": "pong"},
        {"role": "user", "content": "hello"},
    ],
}


def create_request(max_prompt_tokens: Optional[int]):
    return {
        "inputs": [
            {
                **CHAT_COMPLETION_REQUEST,
                "max_prompt_tokens": max_prompt_tokens,
            }
        ]
    }


def create_response(
    model_max_prompt_tokens: int, max_prompt_tokens: Optional[int]
):
    if max_prompt_tokens is None:
        if model_max_prompt_tokens >= 4:
            return {
                "outputs": [{"status": "success", "discarded_messages": []}]
            }
        else:
            return {
                "outputs": [
                    {
                        "status": "error",
                        "error": "Token count of all messages (4) exceeds "
                        f"the model maximum prompt tokens ({model_max_prompt_tokens}).",
                    }
                ]
            }

    if max_prompt_tokens == 1:
        return {
            "outputs": [
                {
                    "status": "error",
                    "error": "Token count of the last user message and all "
                    "system messages (2) exceeds the maximum prompt tokens (1).",
                }
            ]
        }
    if max_prompt_tokens == 2:
        return {
            "outputs": [{"status": "success", "discarded_messages": [1, 2]}]
        }
    if max_prompt_tokens == 3:
        return {"outputs": [{"status": "success", "discarded_messages": [1]}]}
    return {"outputs": [{"status": "success", "discarded_messages": []}]}


deployment = "test-app"

noop = DIALApp().add_chat_completion(deployment, NoopApplication())


def echo(model_max_prompt_tokens: int):
    return DIALApp().add_chat_completion(
        deployment, EchoApplication(model_max_prompt_tokens)
    )


testcases: List[TestCase] = [
    TestCase(
        noop,
        deployment,
        "truncate_prompt",
        create_request(None),
        route_not_found_error,
    ),
    TestCase(
        noop,
        deployment,
        "truncate_prompts",
        create_request(None),
        route_not_found_error,
    ),
    *[
        TestCase(
            echo(4),
            deployment,
            "truncate_prompt",
            create_request(max_prompt_tokens),
            create_response(4, max_prompt_tokens),
        )
        for max_prompt_tokens in range(1, 6)
    ],
    *[
        TestCase(
            echo(model_limit),
            deployment,
            "truncate_prompt",
            create_request(None),
            create_response(model_limit, None),
        )
        for model_limit in [3, 4]
    ],
]


@pytest.mark.parametrize("testcase", testcases)
def test_truncate_prompt(testcase: TestCase):
    run_endpoint_test(testcase)
