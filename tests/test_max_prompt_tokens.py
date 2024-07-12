from unittest.mock import Mock

from starlette.testclient import TestClient

from aidial_sdk import DIALApp
from tests.applications.single_choice import SingleChoiceApplication


def test_max_prompt_tokens_is_set():
    dial_app = DIALApp()
    chat_completion = Mock(wraps=SingleChoiceApplication())
    dial_app.add_chat_completion("test_app", chat_completion)

    test_app = TestClient(dial_app)

    test_app.post(
        "/openai/deployments/test_app/chat/completions",
        json={
            "messages": [{"role": "user", "content": "Test content"}],
            "max_prompt_tokens": 15,
        },
        headers={"Api-Key": "TEST_API_KEY"},
    )

    args, _ = chat_completion.chat_completion.call_args
    request, _ = args

    assert request.max_prompt_tokens == 15


def test_max_prompt_tokens_is_unset():
    dial_app = DIALApp()
    chat_completion = Mock(wraps=SingleChoiceApplication())
    dial_app.add_chat_completion("test_app", chat_completion)

    test_app = TestClient(dial_app)

    test_app.post(
        "/openai/deployments/test_app/chat/completions",
        json={
            "messages": [{"role": "user", "content": "Test content"}],
        },
        headers={"Api-Key": "TEST_API_KEY"},
    )

    args, _ = chat_completion.chat_completion.call_args
    request, _ = args

    assert not request.max_prompt_tokens
