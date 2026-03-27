from collections.abc import MutableMapping
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse, urlunparse

import wrapt
from fastapi import FastAPI
from starlette.types import ASGIApp, Receive, Scope, Send


@dataclass
class FastAPIMiddleware:
    app: ASGIApp
    api_key: ContextVar[str | None]
    conversation_id: ContextVar[str | None]

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        for key, value in scope.get("headers") or []:
            if key == b"api-key":
                self.api_key.set(value.decode("utf-8"))
            if key == b"x-conversation-id":
                self.conversation_id.set(value.decode("utf-8"))

        await self.app(scope, receive, send)


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    port = parsed.port
    scheme = parsed.scheme

    if (scheme, port) in (("http", 80), ("https", 443)):
        netloc = parsed.hostname or ""
    else:
        netloc = parsed.netloc

    return urlunparse(parsed._replace(netloc=netloc))


class HeaderPropagator:
    _app: FastAPI
    _dial_url: str
    _api_key: ContextVar[str | None]
    _conversation_id: ContextVar[str | None]
    _enabled: bool

    _original_requests_send: Any | None
    _original_httpx_build_requests: tuple[Any, Any] | None
    _original_aiohttp_request: Any | None

    def __init__(self, app: FastAPI, dial_url: str):
        self._app = app
        self._dial_url = _normalize_url(dial_url)

        self._api_key = ContextVar("api_key", default=None)
        self._conversation_id = ContextVar("conversation_id", default=None)

        self._enabled = False
        self._original_requests_send = None
        self._original_httpx_build_requests = None
        self._original_aiohttp_request = None

    def enable(self):
        if not self._enabled:
            self._enabled = True
            self._instrument_fast_api(self._app)
            self._instrument_aiohttp()
            self._instrument_requests()
            self._instrument_httpx()

    def disable(self):
        if self._enabled:
            self._enabled = False
            self._deinstrument_aiohttp()
            self._deinstrument_httpx()
            self._deinstrument_requests()

    def _instrument_fast_api(self, app: FastAPI):
        app.add_middleware(
            FastAPIMiddleware,
            api_key=self._api_key,
            conversation_id=self._conversation_id,
        )

    def _instrument_aiohttp(self):
        if self._original_aiohttp_request is not None:
            return

        try:
            import aiohttp
            from multidict import CIMultiDict
        except ImportError:
            return

        def instrumented_request(wrapped, instance, args, kwargs):
            # Method signature: aiohttp.ClientSession._request(self, method, str_or_url, **kwargs)
            url = str(args[1])
            headers = CIMultiDict(kwargs.get("headers") or {})
            self._modify_headers(url, headers)
            if headers:
                kwargs["headers"] = headers

            return wrapped(*args, **kwargs)

        self._original_aiohttp_request = aiohttp.ClientSession._request
        wrapt.wrap_function_wrapper(
            aiohttp.ClientSession, "_request", instrumented_request
        )

    def _deinstrument_aiohttp(self):
        if self._original_aiohttp_request is None:
            return
        import aiohttp

        aiohttp.ClientSession._request = self._original_aiohttp_request
        self._original_aiohttp_request = None

    def _instrument_requests(self):
        if self._original_requests_send is not None:
            return

        try:
            import requests
        except ImportError:
            return

        def instrumented_send(wrapped, instance, args, kwargs):
            request: requests.PreparedRequest = args[0]
            self._modify_headers(request.url or "", request.headers)
            return wrapped(*args, **kwargs)

        self._original_requests_send = requests.Session.send
        wrapt.wrap_function_wrapper(requests.Session, "send", instrumented_send)

    def _deinstrument_requests(self):
        if self._original_requests_send is None:
            return
        import requests

        requests.Session.send = self._original_requests_send
        self._original_requests_send = None

    def _instrument_httpx(self):
        if self._original_httpx_build_requests is not None:
            return

        try:
            import httpx
        except ImportError:
            return

        def instrumented_build_request(wrapped, instance, args, kwargs):
            request: httpx.Request = wrapped(*args, **kwargs)
            self._modify_headers(str(request.url), request.headers)
            return request

        self._original_httpx_build_requests = (
            httpx.Client.build_request,
            httpx.AsyncClient.build_request,
        )
        wrapt.wrap_function_wrapper(
            httpx.Client, "build_request", instrumented_build_request
        )

        wrapt.wrap_function_wrapper(
            httpx.AsyncClient, "build_request", instrumented_build_request
        )

    def _deinstrument_httpx(self):
        if self._original_httpx_build_requests is None:
            return
        import httpx

        client_orig, async_client_orig = self._original_httpx_build_requests
        httpx.Client.build_request = client_orig
        httpx.AsyncClient.build_request = async_client_orig
        self._original_httpx_build_requests = None

    def _modify_headers(
        self, url: str, headers: MutableMapping[str, str]
    ) -> None:
        if _normalize_url(url).startswith(self._dial_url):
            if api_key := self._api_key.get():
                old_api_key = headers.get("api-key")
                old_authz = headers.get("Authorization")

                if (
                    old_api_key
                    and old_authz
                    and old_authz == f"Bearer {old_api_key}"
                ):
                    headers["Authorization"] = f"Bearer {api_key}"

                headers["api-key"] = api_key

            if conversation_id := self._conversation_id.get():
                headers["x-conversation-id"] = conversation_id
