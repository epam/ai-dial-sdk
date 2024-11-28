from typing import Dict

import httpx
from fastapi import FastAPI
from starlette.testclient import TestClient

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion.base import ChatCompletion


def create_app_client(
    chat_completion: ChatCompletion,
    *,
    name: str = "test-deployment-name",
    headers: Dict[str, str] = {"api-key": "TEST_API_KEY"},
) -> httpx.Client:
    app = DIALApp().add_chat_completion(name, chat_completion)
    return create_test_client(app, name=name, headers=headers)


def create_test_client(
    app: FastAPI,
    *,
    name: str = "test-deployment-name",
    headers: Dict[str, str] = {"api-key": "TEST_API_KEY"},
) -> httpx.Client:
    return TestClient(
        app=app,
        headers=headers,
        base_url=f"http://testserver/openai/deployments/{name}",
    )
