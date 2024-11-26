from tests.applications.validator import RequestValidator, ValidatorApplication
from tests.utils.client import create_app_client


def validate_chat_completion(
    request: dict, request_validator: RequestValidator
) -> None:
    client = create_app_client(
        ValidatorApplication(request_validator=request_validator)
    )

    client.post("chat/completions", json=request)
