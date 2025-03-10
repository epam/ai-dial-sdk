import pytest
from fastapi.testclient import TestClient

from aidial_sdk import DIALApp
from tests.applications.validator import ValidatorApplication


@pytest.mark.parametrize("validate", [True, False, None])
def test_top_level_extra_field(validate: bool):
    app = ValidatorApplication(request_validator=lambda r: r.extra_field == "extra_value")  # type: ignore

    dial_app = (
        DIALApp()
        if validate is None
        else DIALApp(validate_extra_request_fields=validate)
    )
    dial_app.add_chat_completion("test-app", app)

    client = TestClient(dial_app)

    actual_response = client.post(
        "/openai/deployments/test-app/chat/completions",
        json={"messages": [], "extra_field": "extra_value"},
        headers={"Api-Key": "TEST_API_KEY"},
    )

    if validate in [None, True]:
        assert actual_response.status_code == 400
        assert actual_response.json() == {
            "error": {
                "code": "400",
                "message": "Your request contained invalid structure on path "
                "extra_field. extra fields not permitted",
                "type": "invalid_request_error",
            }
        }
    else:
        assert actual_response.status_code == 200


@pytest.mark.parametrize("validate", [True, False, None])
def test_message_extra_field(validate: bool):
    app = ValidatorApplication(request_validator=lambda r: r.messages[0].extra_field == "extra_value")  # type: ignore

    dial_app = (
        DIALApp()
        if validate is None
        else DIALApp(validate_extra_request_fields=validate)
    )
    dial_app.add_chat_completion("test-app", app)

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

    if validate in [None, True]:
        assert actual_response.status_code == 400
        assert actual_response.json() == {
            "error": {
                "code": "400",
                "message": "Your request contained invalid structure on path "
                "messages.0.extra_field. extra fields not permitted",
                "type": "invalid_request_error",
            }
        }
    else:
        assert actual_response.status_code == 200
