from typing import Any

import pytest
import respx
from pydantic import BaseModel

from aidial_sdk.http_client import HttpxClient, HttpRequestOptions

@pytest.mark.asyncio
async def test_httpx_client_base_url_not_set():
    client = HttpxClient()
    options = HttpRequestOptions(method="GET", path="/")

    try:
        _ = await client.request(options, BaseModel)
    except ValueError as e:
        assert str(e) == "Base URL is required to make a request. Pls set one in DIALApp"


@pytest.mark.asyncio
async def test_httpx_client_cast_to_none(monkeypatch):
    client = HttpxClient()
    client.set_dial_base_url("https://example.com")
    options = HttpRequestOptions(method="GET", path="/")

    with respx.mock(base_url="https://example.com") as mock:
        mock.get("/").respond(200, json={"message": "success"})

        result = await client.request(options, cast_to=type(None))

        assert result is None


class TestApplication(BaseModel):
    application_properties: dict[str, Any]

    class Config:
        arbitrary_types_allowed = True
        extra = "allow"

@pytest.mark.asyncio
async def test_httpx_client_with_valid_response_cast():
    client = HttpxClient()
    client.set_dial_base_url("https://example.com")
    options = HttpRequestOptions(method="GET", path="/")

    with respx.mock(base_url="https://example.com") as mock:
        mock.get("/").respond(200, json={"application_properties": {"name": "test_name"}})

        response = await client.request(options, cast_to=TestApplication)
        assert isinstance(response, TestApplication)
        assert response.application_properties == {"name": "test_name"}