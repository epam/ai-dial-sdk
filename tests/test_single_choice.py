import json

from fastapi.testclient import TestClient

from aidial_sdk import DIALApp
from tests.applications.signle_choice_application import SingleChoiceApplication


def test_single_choice():
    dial_app = DIALApp()
    dial_app.add_chat_completion("test_app", SingleChoiceApplication())

    test_app = TestClient(dial_app)

    response = test_app.post(
        "/openai/deployments/test_app/chat/completions",
        json={
            "messages": [{"role": "user", "content": "Test content"}],
            "stream": False,
        },
        headers={"Api-Key": "TEST_API_KEY"},
    )

    assert response.status_code == 200 and response.json() == {
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": "123"},
            }
        ],
        "usage": None,
        "id": "test_id",
        "created": 0,
        "object": "chat.completion",
    }


def test_single_choice_streaming():
    dial_app = DIALApp()
    dial_app.add_chat_completion("test_app", SingleChoiceApplication())

    test_app = TestClient(dial_app)

    response = test_app.post(
        "/openai/deployments/test_app/chat/completions",
        json={
            "messages": [{"role": "user", "content": "Test content"}],
            "stream": True,
        },
        headers={"Api-Key": "TEST_API_KEY"},
    )

    for index, value in enumerate(response.iter_lines()):
        if index % 2:
            assert value == ""
            continue

        assert value.startswith("data: ")
        data = value[6:]

        if index == 0:
            assert json.loads(data) == {
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": None,
                        "delta": {"role": "assistant"},
                    }
                ],
                "usage": None,
                "id": "test_id",
                "created": 0,
                "object": "chat.completion.chunk",
            }
        elif index == 2:
            assert json.loads(data) == {
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": None,
                        "delta": {"content": "123"},
                    }
                ],
                "usage": None,
                "id": "test_id",
                "created": 0,
                "object": "chat.completion.chunk",
            }
        elif index == 4:
            assert json.loads(data) == {
                "choices": [{"index": 0, "finish_reason": "stop", "delta": {}}],
                "usage": None,
                "id": "test_id",
                "created": 0,
                "object": "chat.completion.chunk",
            }
        elif index == 6:
            assert data == "[DONE]"
