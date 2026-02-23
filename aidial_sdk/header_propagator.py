from contextvars import ContextVar
from typing import ClassVar, MutableMapping, Optional
from urllib.parse import urlparse, urlunparse

import wrapt
from fastapi import FastAPI
from starlette.types import ASGIApp, Receive, Scope, Send


class FastAPIMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        api_key: ContextVar[Optional[str]],
    ) -> None:
        self.app = app
        self.api_key = api_key

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        for header in scope.get("headers") or []:
            if header[0] == b"api-key":
                self.api_key.set(header[1].decode("utf-8"))

        await self.app(scope, receive, send)


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    port = parsed.port
    scheme = parsed.scheme
    hostname = parsed.hostname or ""

    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        netloc = hostname
    else:
        netloc = parsed.netloc

    return urlunparse(parsed._replace(netloc=netloc))


class HeaderPropagator:
    _app: FastAPI
    _dial_url: str
    _normalized_dial_url: str
    _api_key: ContextVar[Optional[str]]
    _enabled: bool

    _active_instances: ClassVar[list["HeaderPropagator"]] = []
    _requests_wrapper_installed: ClassVar[bool] = False
    _httpx_wrapper_installed: ClassVar[bool] = False

    def __init__(self, app: FastAPI, dial_url: str):
        self._app = app
        self._dial_url = dial_url
        self._normalized_dial_url = _normalize_url(dial_url)

        self._api_key: ContextVar[Optional[str]] = ContextVar(
            "api_key", default=None
        )

        self._enabled = False

    def enable(self):
        if self._enabled:
            return

        self._instrument_fast_api(self._app)
        self._instrument_aiohttp()

        if not HeaderPropagator._requests_wrapper_installed:
            self._instrument_requests()
            HeaderPropagator._requests_wrapper_installed = True

        if not HeaderPropagator._httpx_wrapper_installed:
            self._instrument_httpx()
            HeaderPropagator._httpx_wrapper_installed = True

        HeaderPropagator._active_instances.append(self)
        self._enabled = True

    def disable(self):
        if not self._enabled:
            return

        self._enabled = False
        HeaderPropagator._active_instances.remove(self)

    def _instrument_fast_api(self, app: FastAPI):
        app.add_middleware(FastAPIMiddleware, api_key=self._api_key)

    def _instrument_aiohttp(self):
        try:
            import aiohttp
            from multidict import CIMultiDict
        except ImportError:
            return

        def instrumented_request(wrapped, instance, args, kwargs):
            # aiohttp.ClientSession._request(self, method, str_or_url, **kwargs)
            url = str(args[1])
            headers = CIMultiDict(kwargs.get("headers") or {})
            for prop in HeaderPropagator._active_instances:
                prop._modify_headers(url, headers)
            if headers:
                kwargs["headers"] = headers

            return wrapped(*args, **kwargs)

        wrapt.wrap_function_wrapper(
            aiohttp.ClientSession, "_request", instrumented_request
        )

    def _instrument_requests(self):
        try:
            import requests
        except ImportError:
            return

        def instrumented_send(wrapped, instance, args, kwargs):
            request: requests.PreparedRequest = args[0]
            for prop in HeaderPropagator._active_instances:
                prop._modify_headers(request.url or "", request.headers)
            return wrapped(*args, **kwargs)

        wrapt.wrap_function_wrapper(requests.Session, "send", instrumented_send)

    def _instrument_httpx(self):
        try:
            import httpx
        except ImportError:
            return

        def instrumented_build_request(wrapped, instance, args, kwargs):
            request: httpx.Request = wrapped(*args, **kwargs)
            for prop in HeaderPropagator._active_instances:
                prop._modify_headers(str(request.url), request.headers)
            return request

        wrapt.wrap_function_wrapper(
            httpx.Client, "build_request", instrumented_build_request
        )

        wrapt.wrap_function_wrapper(
            httpx.AsyncClient, "build_request", instrumented_build_request
        )

    def _modify_headers(
        self, url: str, headers: MutableMapping[str, str]
    ) -> None:
        if _normalize_url(url).startswith(self._normalized_dial_url):
            api_key = self._api_key.get()
            if api_key:
                old_api_key = headers.get("api-key")
                old_authz = headers.get("Authorization")

                if (
                    old_api_key
                    and old_authz
                    and old_authz == f"Bearer {old_api_key}"
                ):
                    headers["Authorization"] = f"Bearer {api_key}"

                headers["api-key"] = api_key
