import types
from contextvars import ContextVar
from typing import Optional

import aiohttp
import httpx
import requests
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


class HeaderPropagator:
    _app: FastAPI
    _dial_url: str
    _api_key: ContextVar[Optional[str]]
    _enabled: bool

    def __init__(self, app: FastAPI, dial_url: str):
        self._app = app
        self._dial_url = dial_url

        self._api_key: ContextVar[Optional[str]] = ContextVar(
            "api_key", default=None
        )

        self._enabled = False

    def enable(self):
        if self._enabled:
            return

        self._instrument_fast_api(self._app)
        self._instrument_aiohttp()
        self._instrument_httpx()
        self._instrument_requests()
        self._enabled = True

    def _instrument_fast_api(self, app: FastAPI):
        app.add_middleware(FastAPIMiddleware, api_key=self._api_key)

    def _instrument_aiohttp(self):
        def instrumented_init(wrapped, instance, args, kwargs):
            trace_config = aiohttp.TraceConfig()
            trace_config.on_request_start.append(self._on_aiohttp_request_start)

            trace_configs = list(kwargs.get("trace_configs") or [])
            trace_configs.append(trace_config)

            kwargs["trace_configs"] = trace_configs
            return wrapped(*args, **kwargs)

        wrapt.wrap_function_wrapper(
            aiohttp.ClientSession, "__init__", instrumented_init
        )

    async def _on_aiohttp_request_start(
        self,
        session: aiohttp.ClientSession,
        trace_config_ctx: types.SimpleNamespace,
        params: aiohttp.TraceRequestStartParams,
    ):
        if not str(params.url).startswith(self._dial_url):
            return

        api_key_val = self._api_key.get()
        if api_key_val:
            params.headers["api-key"] = api_key_val

    def _instrument_requests(self):
        def instrumented_send(wrapped, instance, args, kwargs):
            request: requests.PreparedRequest = args[0]
            if request.url and request.url.startswith(self._dial_url):
                api_key_val = self._api_key.get()
                if api_key_val:
                    request.headers["api-key"] = api_key_val

            return wrapped(*args, **kwargs)

        wrapt.wrap_function_wrapper(requests.Session, "send", instrumented_send)

    def _instrument_httpx(self):

        def instrumented_build_request(wrapped, instance, args, kwargs):
            request: httpx.Request = wrapped(*args, **kwargs)
            if request.url and str(request.url).startswith(self._dial_url):
                api_key_val = self._api_key.get()
                if api_key_val:
                    request.headers["api-key"] = api_key_val
            return request

        wrapt.wrap_function_wrapper(
            httpx.Client, "build_request", instrumented_build_request
        )

        wrapt.wrap_function_wrapper(
            httpx.AsyncClient, "build_request", instrumented_build_request
        )
