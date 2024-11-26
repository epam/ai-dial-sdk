from typing import Optional

import httpx
from fastapi import FastAPI
from starlette.testclient import TestClient

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion.base import ChatCompletion


def create_app_client(
    chat_completion: ChatCompletion,
    *,
    name: str = "test-deployment-name",
    api_key: Optional[str] = "TEST_API_KEY",
    heartbeat_interval: Optional[float] = None,
) -> httpx.Client:
    app = DIALApp().add_chat_completion(
        name,
        chat_completion,
        heartbeat_interval=heartbeat_interval,
    )

    return create_test_client(app, name=name, api_key=api_key)


def create_test_client(
    app: FastAPI,
    *,
    name: str = "test-deployment-name",
    api_key: Optional[str] = "TEST_API_KEY",
) -> httpx.Client:
    headers: dict[str, str] = {}
    if api_key:
        headers["Api-Key"] = api_key

    return TestClient(
        app=app,
        headers=headers,
        base_url=f"http://testserver/openai/deployments/{name}",
    )
