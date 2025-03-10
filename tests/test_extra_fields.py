from fastapi.testclient import TestClient

from aidial_sdk import DIALApp
from tests.applications.validator import ValidatorApplication


def test_top_level_extra_field():
    app = ValidatorApplication(request_validator=lambda r: r.extra_field == "extra_value")  # type: ignore

    dial_app = DIALApp().add_chat_completion("test-app", app)

    client = TestClient(dial_app)

    actual_response = client.post(
        "/openai/deployments/test-app/chat/completions",
        json={"messages": [], "extra_field": "extra_value"},
        headers={"Api-Key": "TEST_API_KEY"},
    )

    assert actual_response.status_code == 200


def test_message_extra_field():
    app = ValidatorApplication(request_validator=lambda r: r.messages[0].extra_field == "extra_value")  # type: ignore

    dial_app = DIALApp().add_chat_completion("test-app", app)

    client = TestClient(dial_app)

    actual_response = client.post(
        "/openai/deployments/test-app/chat/completions",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "Test content",
                    "extra_field": "extra_value",
                }
            ]
        },
        headers={"Api-Key": "TEST_API_KEY"},
    )

    assert actual_response.status_code == 200
