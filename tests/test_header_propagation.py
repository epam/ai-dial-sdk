import json
import re
from typing import Optional

import aioresponses
import httpx
import pytest
import requests
import responses
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aidial_sdk.header_propagator import HeaderPropagator
from tests.header_propagation.client import app as sender
from tests.utils.text import removeprefix

DIAL_URL = "http://dial.example.com"
NON_DIAL_URL = "http://non-dial.example.com"
API_KEY = "test-api-key"

URL_PATTERN = re.compile(rf"{re.escape(DIAL_URL)}|{re.escape(NON_DIAL_URL)}")
HOSTS = [removeprefix(url, "http://") for url in [DIAL_URL, NON_DIAL_URL]]


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(sender.router)
    HeaderPropagator(app, DIAL_URL).enable()
    return TestClient(app)


@pytest.fixture
def mock_requests():
    with responses.mock as mock:

        def callback(request: requests.PreparedRequest):
            api_key = request.headers.get("api-key")
            return (
                200,
                {"content-type": "application/json"},
                json.dumps({"api_key": api_key}),
            )

        mock.add_callback(
            responses.GET,
            URL_PATTERN,
            callback=callback,
            content_type="application/json",
        )

        yield mock


@pytest.fixture
def mock_httpx():
    with respx.mock as mock:

        @respx.route(method="GET", host__in=HOSTS, path="/")
        def handler(request: httpx.Request):
            api_key = request.headers.get("api-key")
            return httpx.Response(200, json={"api_key": api_key})

        yield mock


@pytest.fixture
def mock_aiohttp():
    with aioresponses.aioresponses() as mock:

        def callback(url, **kwargs) -> aioresponses.CallbackResult:
            api_key = kwargs.get("headers", {}).get("api-key")
            return aioresponses.CallbackResult(payload={"api_key": api_key})

        mock.get(URL_PATTERN, callback=callback)
        yield mock


@pytest.mark.parametrize(
    "lib", ["aiohttp", "requests", "httpx_sync", "httpx_async"]
)
@pytest.mark.parametrize(
    "url,key_to_send,key_to_receive",
    [
        (DIAL_URL, API_KEY, API_KEY),
        (NON_DIAL_URL, API_KEY, None),
        (DIAL_URL, None, None),
        (NON_DIAL_URL, None, None),
    ],
)
def test_send_request(
    client: TestClient,
    mock_requests,
    mock_httpx,
    mock_aiohttp,
    lib: str,
    url: str,
    key_to_send: Optional[str],
    key_to_receive: Optional[str],
):
    response = client.post(
        "/",
        json={"url": url, "lib": lib},
        headers={} if key_to_send is None else {"api-key": key_to_send},
    )
    assert response.status_code == 200, response.json()

    # NOTE: aioresponses doesn't call trace_configs in the mocked version,
    # and since we are patching the request via a dedicated trace config,
    # we can't test the header propagation for aiohttp.
    # https://github.com/pnuckowski/aioresponses/issues/246
    if lib == "aiohttp":
        key_to_receive = None

    assert response.json() == {"api_key": key_to_receive}
