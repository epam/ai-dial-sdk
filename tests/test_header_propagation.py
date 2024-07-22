import json
import re
from itertools import product
from typing import Mapping, Optional

import aioresponses
import httpx
import pytest
import requests
import responses
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from requests.structures import CaseInsensitiveDict

from aidial_sdk.header_propagator import HeaderPropagator
from aidial_sdk.utils.json import remove_nones
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


def _get_headers(headers: Mapping[str, str]) -> dict:
    api_key = headers.get("Api-Key")
    authz = headers.get("Authorization")
    return remove_nones({"api-key": api_key, "authorization": authz})


@pytest.fixture
def mock_requests():
    with responses.mock as mock:

        def callback(request: requests.PreparedRequest):
            return (
                200,
                {"content-type": "application/json"},
                json.dumps(_get_headers(request.headers)),
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
            return httpx.Response(200, json=_get_headers(request.headers))

        yield mock


@pytest.fixture
def mock_aiohttp():
    with aioresponses.aioresponses() as mock:

        def callback(url, **kwargs) -> aioresponses.CallbackResult:
            headers = CaseInsensitiveDict(kwargs.get("headers", {}))
            return aioresponses.CallbackResult(payload=_get_headers(headers))

        mock.get(URL_PATTERN, callback=callback)
        yield mock


@pytest.mark.parametrize(
    "lib, url, key_to_propagate, key_for_upstream, add_authz",
    product(
        ["aiohttp", "requests", "httpx_sync", "httpx_async"],
        [DIAL_URL, NON_DIAL_URL],
        ["test-api-key", None],
        ["dummy-api-key", None],
        [True, False],
    ),
)
def test_send_request(
    client: TestClient,
    mock_requests,
    mock_httpx,
    mock_aiohttp,
    lib: str,
    url: str,
    key_to_propagate: Optional[str],
    key_for_upstream: Optional[str],
    add_authz: bool,
):
    headers_to_propagate = {}
    if key_to_propagate:
        headers_to_propagate["api-key"] = key_to_propagate
        if add_authz:
            headers_to_propagate["authorization"] = f"Bearer {key_to_propagate}"

    headers_for_upstream = {}
    if key_for_upstream:
        headers_for_upstream["api-key"] = key_for_upstream
        if add_authz:
            headers_for_upstream["authorization"] = f"Bearer {key_for_upstream}"

    response = client.post(
        "/",
        json={"url": url, "lib": lib, "headers": headers_for_upstream},
        headers=headers_to_propagate,
    )
    assert response.status_code == 200, response.json()

    expected_key = (
        key_to_propagate if url == DIAL_URL else None
    ) or key_for_upstream

    expected_headers = {}
    if expected_key:
        expected_headers["api-key"] = expected_key
        if add_authz and key_for_upstream:
            expected_headers["authorization"] = f"Bearer {expected_key}"

    # NOTE: aioresponses doesn't call trace_configs in the mocked version,
    # and since we are patching the request via a dedicated trace config,
    # we can't test the header propagation for aiohttp.
    # https://github.com/pnuckowski/aioresponses/issues/246
    if lib == "aiohttp":
        expected_headers = headers_for_upstream

    assert response.json() == expected_headers
