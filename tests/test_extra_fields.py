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
@pytest.mark.parametrize("stream", [True, False])
def test_extra_field_top_level(allow_extra: bool, stream: bool):
    client = _create_client(
        allow_extra,
        lambda r: r.extra_field == "extra_value",  # type: ignore
    )

    response = client.post(
        "chat/completions",
        json={
            "messages": [{"role": "user", "content": "Test content"}],
            "extra_field": "extra_value",
            "stream": stream,
        },
    )

    if allow_extra in [None, False]:
        expected_response = extra_fields_error("extra_field")
        assert response.status_code == expected_response.code
        assert response.json() == expected_response.error
    else:
        assert response.status_code == 200


@pytest.mark.parametrize("allow_extra", [True, False, None])
@pytest.mark.parametrize("stream", [True, False])
def test_extra_field_message(allow_extra: bool, stream: bool):
    client = _create_client(
        allow_extra,
        lambda r: r.messages[0].extra_field == "extra_value",  # type: ignore
    )

    response = client.post(
        "chat/completions",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "Test content",
                    "extra_field": "extra_value",
                }
            ],
            "stream": stream,
        },
    )

    if allow_extra in [None, False]:
        expected_response = extra_fields_error("messages.0.extra_field")
        assert response.status_code == expected_response.code
        assert response.json() == expected_response.error
    else:
        assert response.status_code == 200


@pytest.mark.parametrize("allow_extra", [True, False, None])
@pytest.mark.parametrize("stream", [True, False])
def test_extra_two_fields(allow_extra: bool, stream: bool):
    client = _create_client(
        allow_extra,
        lambda r: r.extra_field1 == "extra_value1"  # type: ignore
        and r.messages[0].extra_field2 == "extra_value2",  # type: ignore
    )

    response = client.post(
        "chat/completions",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "Test content",
                    "extra_field2": "extra_value2",
                }
            ],
            "extra_field1": "extra_value1",
            "stream": stream,
        },
    )

    if allow_extra in [None, False]:
        expected_response = extra_fields_error("extra_field1")
        assert response.status_code == expected_response.code
        assert response.json() == expected_response.error
    else:
        assert response.status_code == 200
