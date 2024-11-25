from starlette.testclient import TestClient

from aidial_sdk import DIALApp
from tests.applications.single_choice import SingleChoiceApplication
from tests.utils.chunks import check_sse_stream, create_single_choice_chunk


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
                "message": {
                    "role": "assistant",
                    "content": "Test response content",
                },
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

    check_sse_stream(
        list(response.iter_lines()),
        [
            create_single_choice_chunk({"role": "assistant"}),
            create_single_choice_chunk({"content": "Test response content"}),
            create_single_choice_chunk({}, "stop"),
        ],
    )
