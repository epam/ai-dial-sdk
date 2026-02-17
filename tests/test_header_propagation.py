import contextlib
import json
from dataclasses import dataclass, field
from itertools import product
from typing import Any, Generator, Literal, Mapping, Optional

import aioresponses
import httpx
import pytest
import requests
import responses
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from requests.structures import CaseInsensitiveDict
from typing_extensions import assert_never

from aidial_sdk.header_propagator import HeaderPropagator
from aidial_sdk.utils.json import remove_nones
from tests.header_propagation.client import app as sender


@dataclass
class Urls:
    dial_url: str
    matching_urls: list[str] = field(default_factory=list)
    non_matching_urls: list[str] = field(default_factory=list)

    def to_gen(self) -> Generator[tuple[str, bool], Any, Any]:
        for m in self.matching_urls:
            yield (m, True)
        for m in self.non_matching_urls:
            yield (m, False)


_non_dial_url = "http://external.com"

_http_upstream_urls = [
    "http://dial.com",
    "http://dial.com/foo/bar",
    "http://dial.com:80/foo/bar",
]

_https_upstream_urls = [
    "https://dial.com",
    "https://dial.com/foo/bar",
    "https://dial.com:443/foo/bar",
]

_urls = [
    Urls("http://dial.com", _http_upstream_urls, [_non_dial_url]),
    Urls("http://dial.com:80", _http_upstream_urls, [_non_dial_url]),
    Urls("https://dial.com", _https_upstream_urls, [_non_dial_url]),
    Urls("https://dial.com:443", _https_upstream_urls, [_non_dial_url]),
]


@contextlib.contextmanager
def create_client(dial_url: str):
    app = FastAPI()
    app.include_router(sender.router)
    prop = HeaderPropagator(app, dial_url)
    prop.enable()
    yield TestClient(app)
    prop.disable()


def _get_headers(headers: Mapping[str, str]) -> dict:
    api_key = headers.get("Api-Key")
    authz = headers.get("Authorization")
    return remove_nones({"api-key": api_key, "authorization": authz})


@contextlib.contextmanager
def mock_requests(url: str):
    with responses.mock as mock:

        def callback(request: requests.PreparedRequest):
            return (
                200,
                {"content-type": "application/json"},
                json.dumps(_get_headers(request.headers)),
            )

        mock.add_callback(
            responses.GET,
            url,
            callback=callback,
            content_type="application/json",
        )

        yield


@contextlib.contextmanager
def mock_httpx(url: str):
    with respx.mock as mock:

        @mock.route(method="GET", url=url)
        def handler(request: httpx.Request):
            return httpx.Response(200, json=_get_headers(request.headers))

        yield


@contextlib.contextmanager
def mock_aiohttp(url: str):
    with aioresponses.aioresponses() as mock:

        def callback(url, **kwargs) -> aioresponses.CallbackResult:
            headers = CaseInsensitiveDict(kwargs.get("headers", {}))
            return aioresponses.CallbackResult(payload=_get_headers(headers))

        mock.get(url, callback=callback)
        yield


Lib = Literal["aiohttp", "requests", "httpx_sync", "httpx_async"]


@contextlib.contextmanager
def mock_upstream(lib: Lib, url: str):
    match lib:
        case "aiohttp":
            with mock_aiohttp(url):
                yield
        case "httpx_sync" | "httpx_async":
            with mock_httpx(url):
                yield
        case "requests":
            with mock_requests(url):
                yield
        case _:
            assert_never(lib)


@dataclass
class TestCase:
    __test__ = False

    lib: Lib
    dial_url: str
    upstream_url: str
    key_to_propagate: Optional[str]
    key_for_upstream: Optional[str]
    add_authz: bool

    _urls_are_matching: bool

    @classmethod
    def get_test_cases(cls):
        for urls in _urls:
            for upstream_url, is_matching in urls.to_gen():
                for (
                    lib,
                    key_to_propagate,
                    key_for_upstream,
                    add_authz,
                ) in product(
                    ["aiohttp", "requests", "httpx_sync", "httpx_async"],
                    ["test-api-key", None],
                    ["dummy-api-key", None],
                    [True, False],
                ):
                    yield cls(
                        lib=lib,  # type: ignore
                        dial_url=urls.dial_url,
                        upstream_url=upstream_url,
                        key_to_propagate=key_to_propagate,
                        key_for_upstream=key_for_upstream,
                        add_authz=add_authz,
                        _urls_are_matching=is_matching,
                    )

    @property
    def expected_headers(self) -> dict:
        expected_key = (
            self.key_to_propagate if self._urls_are_matching else None
        ) or self.key_for_upstream

        ret = {}
        if expected_key:
            ret["api-key"] = expected_key
            if self.add_authz and self.key_for_upstream:
                ret["authorization"] = f"Bearer {expected_key}"

        return ret

    def get_id(self) -> str:
        return f"{self.lib}-{self.dial_url}-{self.upstream_url}-{self.key_to_propagate}-{self.key_for_upstream}-{self.add_authz}"


@pytest.mark.parametrize(
    "tc", TestCase.get_test_cases(), ids=lambda ts: ts.get_id()
)
def test_send_request(tc: TestCase):
    with (
        mock_upstream(tc.lib, tc.upstream_url),
        create_client(tc.dial_url) as client,
    ):
        headers_to_propagate = {}
        if tc.key_to_propagate:
            headers_to_propagate["api-key"] = tc.key_to_propagate
            if tc.add_authz:
                headers_to_propagate["authorization"] = (
                    f"Bearer {tc.key_to_propagate}"
                )

        headers_for_upstream = {}
        if tc.key_for_upstream:
            headers_for_upstream["api-key"] = tc.key_for_upstream
            if tc.add_authz:
                headers_for_upstream["authorization"] = (
                    f"Bearer {tc.key_for_upstream}"
                )

        response = client.post(
            "/",
            json={
                "url": tc.upstream_url,
                "lib": tc.lib,
                "headers": headers_for_upstream,
            },
            headers=headers_to_propagate,
        )

        assert response.status_code == 200
        assert response.json() == tc.expected_headers
