from typing import List, Optional

import pytest

from tests.applications.echo_application import EchoApplication
from tests.applications.single_choice_application import SingleChoiceApplication
from tests.utils.endpoint_test import TestCase, run_endpoint_test_case
from tests.utils.errors import not_implemented_error, route_not_found_error

CHAT_COMPLETION_REQUEST = {
    "messages": [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "ping"},
        {"role": "assistant", "content": "pong"},
        {"role": "user", "content": "hello"},
    ],
}


def get_truncate_prompt_request(max_prompt_tokens: Optional[int]):
    return {
        "requests": [
            {
                **CHAT_COMPLETION_REQUEST,
                "max_prompt_tokens": max_prompt_tokens,
            }
        ]
    }


def get_truncate_prompt_response(
    model_max_prompt_tokens: int,
    max_prompt_tokens: Optional[int],
):
    if max_prompt_tokens is None:
        if model_max_prompt_tokens >= 4:
            return {
                "responses": [{"status": "success", "discarded_messages": []}]
            }
        else:
            return {
                "responses": [
                    {
                        "status": "error",
                        "error": f"Token count of all messages (4) exceeds the model maximum prompt tokens ({model_max_prompt_tokens}).",
                    }
                ]
            }

    if max_prompt_tokens == 1:
        return {
            "responses": [
                {
                    "status": "error",
                    "error": "Token count of the last user message and all system messages (2) exceeds the maximum prompt tokens (1).",
                }
            ]
        }
    if max_prompt_tokens == 2:
        return {
            "responses": [{"status": "success", "discarded_messages": [1, 2]}]
        }
    if max_prompt_tokens == 3:
        return {"responses": [{"status": "success", "discarded_messages": [1]}]}
    return {"responses": [{"status": "success", "discarded_messages": []}]}


simple = SingleChoiceApplication()
echo = EchoApplication

testcases: List[TestCase] = [
    TestCase(
        simple,
        "truncate_prompt",
        get_truncate_prompt_request(None),
        not_implemented_error("truncate_prompt"),
    ),
    TestCase(
        simple,
        "truncate_prompts",
        get_truncate_prompt_request(None),
        route_not_found_error,
    ),
    *[
        TestCase(
            echo(4),
            "truncate_prompt",
            get_truncate_prompt_request(max_prompt_tokens),
            get_truncate_prompt_response(4, max_prompt_tokens),
        )
        for max_prompt_tokens in range(1, 6)
    ],
    *[
        TestCase(
            echo(model_limit),
            "truncate_prompt",
            get_truncate_prompt_request(None),
            get_truncate_prompt_response(model_limit, None),
        )
        for model_limit in [3, 4]
    ],
]


@pytest.mark.parametrize("testcase", testcases)
def test_truncate_prompt(testcase: TestCase):
    run_endpoint_test_case(testcase)
