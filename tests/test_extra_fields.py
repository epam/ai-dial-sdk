import pytest
from fastapi.testclient import TestClient

from aidial_sdk import DIALApp
from tests.applications.validator import RequestValidator, ValidatorApplication
from tests.utils.errors import extra_fields_error


def _create_client(allow_extra: bool, validator: RequestValidator):
    dial_app = (
        DIALApp()
        if allow_extra is None
        else DIALApp(allow_extra_request_fields=allow_extra)
    ).add_chat_completion(
        "test-app", ValidatorApplication(request_validator=validator)
    )

    return TestClient(
        dial_app,
        headers={"Api-Key": "TEST_API_KEY"},
        base_url="http://testserver/openai/deployments/test-app",
    )


@pytest.mark.parametrize("allow_extra", [True, False, None])
def test_top_level_extra_field(allow_extra: bool):

    client = _create_client(allow_extra, lambda r: r.extra_field == "extra_value")  # type: ignore

    response = client.post(
        "chat/completions",
        json={"messages": [], "extra_field": "extra_value"},
    )

    if allow_extra in [None, False]:
        expected_response = extra_fields_error("extra_field")
        assert response.status_code == expected_response.code
        assert response.json() == expected_response.error
    else:
        assert response.status_code == 200


@pytest.mark.parametrize("allow_extra", [True, False, None])
def test_message_extra_field(allow_extra: bool):
    client = _create_client(allow_extra, lambda r: r.messages[0].extra_field == "extra_value")  # type: ignore

    response = client.post(
        "chat/completions",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "Test content",
                    "extra_field": "extra_value",
                }
            ]
        },
    )

    if allow_extra in [None, False]:
        expected_response = extra_fields_error("messages.0.extra_field")
        assert response.status_code == expected_response.code
        assert response.json() == expected_response.error
    else:
        assert response.status_code == 200
