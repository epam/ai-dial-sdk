import fastapi

from aidial_sdk._pydantic import SecretStr
from aidial_sdk.chat_completion import Request
from aidial_sdk.deployment._headers import DIAL_DEPLOYMENT_ID

# The deployment the test clients call by default
DEPLOYMENT_NAME = "test-deployment-name"

_DUMMY_FASTAPI_REQUEST = fastapi.Request({"type": "http"})

DUMMY_DIAL_REQUEST = Request(
    headers={DIAL_DEPLOYMENT_ID: "dummy-deployment"},
    original_request=_DUMMY_FASTAPI_REQUEST,
    api_key_secret=SecretStr("dummy_key"),
    deployment_id="",
    messages=[],
)
