import fastapi

from aidial_sdk.chat_completion import Request
from aidial_sdk.pydantic_v1 import SecretStr

_DUMMY_FASTAPI_REQUEST = fastapi.Request({"type": "http"})

DUMMY_DIAL_REQUEST = Request(
    headers={},
    original_request=_DUMMY_FASTAPI_REQUEST,
    api_key_secret=SecretStr("dummy_key"),
    deployment_id="",
    messages=[],
)
