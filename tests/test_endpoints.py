from typing import List, Optional, Tuple, Union

import pytest
from starlette.testclient import TestClient

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion.base import ChatCompletion
from tests.applications.echo_application import EchoApplication
from tests.applications.single_choice_application import SingleChoiceApplication
from tests.utils.errors import (
    Error,
    bad_request_error,
    extra_fields_error,
    not_implemented_error,
    route_not_found_error,
)

CHAT_COMPLETION_REQUEST = {
    "messages": [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "ping"},
        {"role": "assistant", "content": "pong"},
        {"role": "user", "content": "hello"},
    ],
}

TOKENIZE_REQUEST_OK1 = {"requests": [CHAT_COMPLETION_REQUEST, "test string"]}
TOKENIZE_RESPONSE_OK1 = {
    "responses": [
        {"status": "success", "token_count": 4},
        {"status": "success", "token_count": 2},
    ]
}

TOKENIZE_REQUEST_OK2 = {"requests": []}
TOKENIZE_RESPONSE_OK2 = {"responses": []}

TOKENIZE_REQUEST_FAIL = {"requests": [{}]}
TOKENIZE_RESPONSE_FAIL = {
    "responses": [
        {
            "status": "error",
            "error": "Request must contain either 'requests' or 'request'",
        }
    ]
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


RATE_REQUEST_OK1 = {}
RATE_REQUEST_OK2 = {"responseId": "0", "rate": True}
RATE_REQUEST_FAIL = {"foo": "bar"}


simple = SingleChoiceApplication()
echo = EchoApplication

TestCase = Tuple[ChatCompletion, str, dict, Union[Error, dict, None]]

testcases: List[TestCase] = [
    (simple, "rate", RATE_REQUEST_OK2, None),
    (simple, "rate", RATE_REQUEST_OK1, None),
    (simple, "rate", RATE_REQUEST_FAIL, extra_fields_error("foo")),
    (
        simple,
        "tokenize",
        TOKENIZE_REQUEST_OK1,
        not_implemented_error("tokenize"),
    ),
    (
        simple,
        "truncate_prompt",
        get_truncate_prompt_request(None),
        not_implemented_error("truncate_prompt"),
    ),
    (simple, "tokenizer", TOKENIZE_REQUEST_OK1, route_not_found_error),
    (
        simple,
        "truncate_prompts",
        get_truncate_prompt_request(None),
        route_not_found_error,
    ),
    (echo(0), "rate", RATE_REQUEST_OK2, None),
    (echo(0), "rate", RATE_REQUEST_OK1, None),
    (echo(0), "rate", RATE_REQUEST_FAIL, extra_fields_error("foo")),
    (echo(0), "tokenize", TOKENIZE_REQUEST_OK1, TOKENIZE_RESPONSE_OK1),
    (echo(0), "tokenize", TOKENIZE_REQUEST_OK2, TOKENIZE_RESPONSE_OK2),
    (
        echo(0),
        "tokenize",
        TOKENIZE_REQUEST_FAIL,
        bad_request_error("requests.0.messages"),
    ),
    *[
        (
            echo(4),
            "truncate_prompt",
            get_truncate_prompt_request(max_prompt_tokens),
            get_truncate_prompt_response(4, max_prompt_tokens),
        )
        for max_prompt_tokens in range(1, 6)
    ],
    *[
        (
            echo(model_limit),
            "truncate_prompt",
            get_truncate_prompt_request(None),
            get_truncate_prompt_response(model_limit, None),
        )
        for model_limit in [3, 4]
    ],
]


@pytest.mark.parametrize(
    "app, endpoint, request_body, expected_response_body",
    testcases,
)
def test_endpoints(app, endpoint, request_body, expected_response_body):
    dial_app = DIALApp()
    dial_app.add_chat_completion("test_app", app)

    test_app = TestClient(dial_app)

    actual_response = test_app.post(
        f"/openai/deployments/test_app/{endpoint}",
        json=request_body,
        headers={"Api-Key": "TEST_API_KEY"},
    )

    if actual_response.text == "":
        actual_response_body = None
    else:
        actual_response_body = actual_response.json()

    if isinstance(expected_response_body, Error):
        expected_response_code = expected_response_body.code
        expected_response_body = expected_response_body.error
    else:
        expected_response_code = 200

    assert actual_response.status_code == expected_response_code
    assert actual_response_body == expected_response_body
