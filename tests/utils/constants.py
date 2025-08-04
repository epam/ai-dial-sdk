import fastapi

from aidial_sdk._pydantic import SecretStr
from aidial_sdk.chat_completion import Request

_DUMMY_FASTAPI_REQUEST = fastapi.Request({"type": "http"})

DUMMY_DIAL_REQUEST = Request(
    headers={},
    original_request=_DUMMY_FASTAPI_REQUEST,
    api_key_secret=SecretStr("dummy_key"),
    deployment_id="",
    messages=[],
)
