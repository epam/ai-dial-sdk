import httpx2
from fastapi import FastAPI
from starlette.testclient import TestClient

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion.base import ChatCompletion
from aidial_sdk.deployment._headers import DIAL_DEPLOYMENT_ID
from tests.utils import virtual_clock
from tests.utils.constants import DEPLOYMENT_NAME


def create_app_client(
    chat_completion: ChatCompletion,
    *,
    name: str = DEPLOYMENT_NAME,
    headers: dict[str, str] = {"api-key": "TEST_API_KEY"},
) -> httpx2.Client:
    app = DIALApp().add_chat_completion(name, chat_completion)
    return create_test_client(app, name=name, headers=headers)


def _with_deployment_id(
    headers: dict[str, str], deployment: str
) -> dict[str, str]:
    # DIAL Core always tells the app the deployment the request is for.
    # Headers are case-insensitive, so the given ones override it in any case.
    ret = httpx2.Headers({DIAL_DEPLOYMENT_ID: deployment})
    ret.update(headers)
    return dict(ret)


def create_test_client(
    app: FastAPI,
    *,
    name: str = DEPLOYMENT_NAME,
    headers: dict[str, str] = {"api-key": "TEST_API_KEY"},
) -> httpx2.Client:
    return TestClient(
        app=app,
        headers=_with_deployment_id(headers, name),
        base_url=f"http://testserver/openai/deployments/{name}",
        backend_options=virtual_clock.backend_options(),
    )
