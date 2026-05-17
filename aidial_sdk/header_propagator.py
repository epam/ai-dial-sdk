import types
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
    headers_to_proxy: list[str]
    request_headers: ContextVar[dict[str, str] | None]

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        headers: dict[str, str] = {}
        for key, value in scope.get("headers") or []:
            key = key.decode("utf-8")
            value = value.decode("utf-8")
            if key in self.headers_to_proxy:
                headers[key] = value

        self.request_headers.set(headers)

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

    _headers_to_proxy: list[str]
    _request_headers: ContextVar[dict[str, str] | None]

    _enabled: bool

    _original_requests_send: Any | None
    _original_httpx_build_requests: tuple[Any, Any] | None
    _original_aiohttp_init: Any | None

    def __init__(
        self,
        app: FastAPI,
        *,
        dial_url: str,
        proxy_auth_headers: bool,
        headers_to_proxy: list[str],
    ):
        self._app = app
        self._dial_url = _normalize_url(dial_url)

        self._headers_to_proxy = [s.lower() for s in headers_to_proxy]
        if proxy_auth_headers:
            self._headers_to_proxy.append("api-key")

        self._request_headers = ContextVar("request_headers", default=None)

        self._enabled = False
        self._original_requests_send = None
        self._original_httpx_build_requests = None
        self._original_aiohttp_init = None

    @property
    def is_noop(self) -> bool:
        return not self._headers_to_proxy

    def enable(self):
        if not self.is_noop and not self._enabled:
            self._enabled = True
            self._instrument_fast_api(self._app)
            self._instrument_aiohttp()
            self._instrument_requests()
            self._instrument_httpx()

    def disable(self):
        if not self.is_noop and self._enabled:
            self._enabled = False
            self._deinstrument_aiohttp()
            self._deinstrument_httpx()
            self._deinstrument_requests()

    def _instrument_fast_api(self, app: FastAPI):
        app.add_middleware(
            FastAPIMiddleware,
            headers_to_proxy=self._headers_to_proxy,
            request_headers=self._request_headers,
        )

    def _instrument_aiohttp(self):
        if self._original_aiohttp_init is not None:
            return

        try:
            import aiohttp
        except ImportError:
            return

        async def _on_request_start(
            session: aiohttp.ClientSession,
            trace_config_ctx: types.SimpleNamespace,
            params: aiohttp.TraceRequestStartParams,
        ):
            self._modify_headers(str(params.url), params.headers)

        def instrumented_init(wrapped, instance, args, kwargs):
            trace_config = aiohttp.TraceConfig()
            trace_config.on_request_start.append(_on_request_start)

            trace_configs = list(kwargs.get("trace_configs") or [])
            trace_configs.append(trace_config)

            kwargs["trace_configs"] = trace_configs
            return wrapped(*args, **kwargs)

        self._original_aiohttp_init = aiohttp.ClientSession.__init__
        wrapt.wrap_function_wrapper(
            aiohttp.ClientSession, "__init__", instrumented_init
        )

    def _deinstrument_aiohttp(self):
        if self._original_aiohttp_init is None:
            return
        import aiohttp

        aiohttp.ClientSession.__init__ = self._original_aiohttp_init
        self._original_aiohttp_init = None

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
        if not _normalize_url(url).startswith(self._dial_url):
            return

        request_headers = self._request_headers.get() or {}

        for header, value in request_headers.items():
            if header == "api-key":
                old_api_key = headers.get("api-key")
                old_authz = headers.get("Authorization")

                if (
                    old_api_key
                    and old_authz
                    and old_authz == f"Bearer {old_api_key}"
                ):
                    headers["Authorization"] = f"Bearer {value}"

                headers["api-key"] = value

            elif header not in headers:
                headers[header] = value
