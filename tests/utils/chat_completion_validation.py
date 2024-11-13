from fastapi.testclient import TestClient

from aidial_sdk.application import DIALApp
from tests.applications.validator import RequestValidator, ValidatorApplication


def validate_chat_completion(
    input_request: dict,
    request_validator: RequestValidator,
) -> None:
    dial_app = DIALApp()
    dial_app.add_chat_completion(
        "test_app",
        ValidatorApplication(
            request_validator=request_validator,
        ),
    )

    test_app = TestClient(dial_app)

    test_app.post(
        "/openai/deployments/test_app/chat/completions",
        json=input_request,
        headers={"Api-Key": "TEST_API_KEY"},
    )
