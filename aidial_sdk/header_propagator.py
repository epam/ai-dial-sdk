import functools
import types
from contextvars import ContextVar
from typing import Optional

import aiohttp
import wrapt
from fastapi import FastAPI
from requests import PreparedRequest
from requests.sessions import Session
from starlette.middleware.exceptions import ExceptionMiddleware


class FastAPIMiddleware:
    def __init__(
        self,
        app: ExceptionMiddleware,
        api_key: ContextVar[Optional[str]],
        authorization: ContextVar[Optional[str]],
    ) -> None:
        self.app = app
        self.api_key = api_key
        self.authorization = authorization

    async def __call__(self, scope, receive, send) -> None:
        for header in scope["headers"]:
            if header[0] == b"api-key":
                self.api_key.set(header[1].decode("utf-8"))
            elif header[0] == b"authorization":
                self.authorization.set(header[1].decode("utf-8"))

        await self.app(scope, receive, send)


class HeaderPropagator:
    _app: FastAPI
    _dial_url: str
    _api_key: ContextVar[Optional[str]]
    _authorization: ContextVar[Optional[str]]
    _enabled: bool

    def __init__(self, app: FastAPI, dial_url: str):
        self._app = app
        self._dial_url = dial_url

        self._api_key: ContextVar[Optional[str]] = ContextVar(
            "api_key", default=None
        )
        self._authorization: ContextVar[Optional[str]] = ContextVar(
            "authorization", default=None
        )

        self._enabled = False

    def enable(self):
        if self._enabled:
            return

        self._instrument_fast_api(self._app)
        self._instrument_aiohttp()
        self._instrument_requests()
        self._enabled = True

    def _instrument_fast_api(self, app: FastAPI):
        app.add_middleware(
            FastAPIMiddleware,
            api_key=self._api_key,
            authorization=self._authorization,
        )

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
        unused_session: aiohttp.ClientSession,
        trace_config_ctx: types.SimpleNamespace,
        params: aiohttp.TraceRequestStartParams,
    ):
        if not str(params.url).startswith(self._dial_url):
            return

        api_key_val = self._api_key.get()
        authorization_val = self._authorization.get()

        if api_key_val:
            params.headers["api-key"] = api_key_val
        if authorization_val:
            params.headers["authorization"] = authorization_val

    def _instrument_requests(self):
        wrapped_send = Session.send

        @functools.wraps(wrapped_send)
        def instrumented_send(self, request: PreparedRequest, **kwargs):
            if request.url and request.url.startswith(self._dial_url):
                api_key_val = self._dial_api_key.get()
                authorization_val = self._dial_authorization.get()

                if api_key_val:
                    request.headers["api-key"] = api_key_val
                if authorization_val:
                    request.headers["authorization"] = authorization_val

            return wrapped_send(self, request, **kwargs)

        Session._dial_url = self._dial_url  # type: ignore
        Session._dial_api_key = self._api_key  # type: ignore
        Session._dial_authorization = self._authorization  # type: ignore
        Session.send = instrumented_send
