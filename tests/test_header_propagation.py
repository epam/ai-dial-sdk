import contextlib
import json
from collections.abc import Generator, Mapping
from dataclasses import dataclass, field
from itertools import product
from typing import Any, Literal

import aiointercept
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

    def to_gen(self) -> Generator[tuple[str, str, bool], Any, Any]:
        for m in self.matching_urls:
            yield (self.dial_url, m, True)
        for m in self.non_matching_urls:
            yield (self.dial_url, m, False)


def _all_urls() -> Generator[tuple[str, str, bool], Any, Any]:
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

    for url in _urls:
        yield from url.to_gen()


@contextlib.contextmanager
def create_client(
    dial_url: str,
    proxy_auth_headers: bool = False,
    headers_to_proxy: list[str] | None = None,
):
    app = FastAPI()
    app.include_router(sender.router)
    prop = HeaderPropagator(
        app,
        dial_url=dial_url,
        proxy_auth_headers=proxy_auth_headers,
        headers_to_proxy=headers_to_proxy or [],
    )
    prop.enable()
    yield TestClient(app)
    prop.disable()


def _get_headers(headers: Mapping[str, str]) -> dict:
    ret = {}
    for header in ("Api-Key", "Authorization", "X-Conversation-ID"):
        if value := headers.get(header):
            ret[header.lower()] = value
    return ret


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


@contextlib.asynccontextmanager
async def mock_aiohttp(url: str):
    async with aiointercept.aiointercept(True) as mock:

        def callback(url, **kwargs) -> aiointercept.CallbackResult:
            headers = CaseInsensitiveDict(kwargs.get("headers", {}))
            return aiointercept.CallbackResult(payload=_get_headers(headers))

        mock.get(url, callback=callback)
        yield


Lib = Literal["aiohttp", "requests", "httpx_sync", "httpx_async"]


@contextlib.asynccontextmanager
async def mock_upstream(lib: Lib, url: str):
    match lib:
        case "aiohttp":
            async with mock_aiohttp(url):
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

    dial_url: str
    upstream_url: str
    key_for_dial_app: str | None
    key_for_upstream: str | None
    add_authz: bool

    _urls_are_matching: bool

    @classmethod
    def get_test_cases(cls):
        for dial_url, upstream_url, is_matching in _all_urls():
            for key_for_dial_app, key_for_upstream, add_authz in product(
                ["test-api-key", None],
                ["dummy-api-key", None],
                [True, False],
            ):
                yield cls(
                    dial_url=dial_url,
                    upstream_url=upstream_url,
                    key_for_dial_app=key_for_dial_app,
                    key_for_upstream=key_for_upstream,
                    add_authz=add_authz,
                    _urls_are_matching=is_matching,
                )

    @property
    def expected_headers(self) -> dict:
        expected_key = (
            self.key_for_dial_app if self._urls_are_matching else None
        ) or self.key_for_upstream

        ret = {}
        if expected_key:
            ret["api-key"] = expected_key
            if self.add_authz and self.key_for_upstream:
                ret["authorization"] = f"Bearer {expected_key}"

        return ret

    def get_id(self) -> str:
        return "-".join(
            [
                self.dial_url,
                self.upstream_url,
                str(self.key_for_dial_app),
                str(self.key_for_upstream),
                str(self.add_authz),
            ]
        )


@pytest.mark.parametrize(
    "lib", ["aiohttp", "requests", "httpx_sync", "httpx_async"]
)
@pytest.mark.parametrize(
    "tc", TestCase.get_test_cases(), ids=lambda ts: ts.get_id()
)
async def test_api_key_propagation(lib: Lib, tc: TestCase):
    async with mock_upstream(lib, tc.upstream_url):
        with create_client(tc.dial_url, proxy_auth_headers=True) as client:
            headers_for_dial_app = {}
            if tc.key_for_dial_app:
                headers_for_dial_app["aPi-kEy"] = tc.key_for_dial_app
                if tc.add_authz:
                    headers_for_dial_app["auThorIzaTion"] = (
                        f"Bearer {tc.key_for_dial_app}"
                    )

            headers_for_upstream = {}
            if tc.key_for_upstream:
                headers_for_upstream["apI-keY"] = tc.key_for_upstream
                if tc.add_authz:
                    headers_for_upstream["AuthoRization"] = (
                        f"Bearer {tc.key_for_upstream}"
                    )

            response = client.post(
                "/",
                json={
                    "url": tc.upstream_url,
                    "lib": lib,
                    "headers": headers_for_upstream,
                },
                headers=headers_for_dial_app,
            )

        assert response.status_code == 200
        assert response.json() == tc.expected_headers


@pytest.mark.parametrize(
    "lib", ["aiohttp", "requests", "httpx_sync", "httpx_async"]
)
@pytest.mark.parametrize("dial_url, upstream_url, is_matching", _all_urls())
@pytest.mark.parametrize(
    "header_for_dial_app", [None, "x-conversion-id-for-dial-app"]
)
@pytest.mark.parametrize(
    "header_for_upstream", [None, "x-conversion-id-for-upstream"]
)
async def test_conversation_id_propagation(
    lib: Lib,
    dial_url: str,
    upstream_url: str,
    is_matching: bool,
    header_for_dial_app: str | None,
    header_for_upstream: str | None,
):
    async with mock_upstream(lib, upstream_url):
        with create_client(
            dial_url, headers_to_proxy=["x-conVerSation-id"]
        ) as client:
            headers_for_dial_app = remove_nones(
                {"x-ConVersaTion-Id": header_for_dial_app}
            )
            headers_for_upstream = remove_nones(
                {"x-cOnvErsAtion-iD": header_for_upstream}
            )

            response = client.post(
                "/",
                json={
                    "url": upstream_url,
                    "lib": lib,
                    "headers": headers_for_upstream,
                },
                headers=headers_for_dial_app,
            )

            expected_value = None
            if header_for_upstream:
                expected_value = header_for_upstream
            elif is_matching and header_for_dial_app:
                expected_value = header_for_dial_app

            expected_headers = remove_nones({"x-conversation-id": expected_value})

        assert response.status_code == 200
        assert response.json() == expected_headers
