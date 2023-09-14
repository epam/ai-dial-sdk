import functools
import types
from contextvars import ContextVar
from typing import Optional

import aiohttp
import wrapt
from fastapi import FastAPI
from requests import PreparedRequest
from requests.sessions import Session


class FastAPIMiddleware:
    def __init__(self, app, api_key, authorization) -> None:
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


class HeaderPropagation:
    _dial_url: str

    def __init__(self, app: FastAPI, dial_url: str):
        self._dial_url = dial_url

        self.api_key: ContextVar[Optional[str]] = ContextVar(
            "api_key", default=None
        )
        self.authorization: ContextVar[Optional[str]] = ContextVar(
            "authorization", default=None
        )

        # FastApi
        app.add_middleware(
            FastAPIMiddleware,
            api_key=self.api_key,
            authorization=self.authorization,
        )

        # aiohttp
        def instrumented_init(wrapped, instance, args, kwargs):
            trace_config = aiohttp.TraceConfig()
            trace_config.on_request_start.append(self.on_request_start)

            trace_configs = list(kwargs.get("trace_configs") or [])
            trace_configs.append(trace_config)

            kwargs["trace_configs"] = trace_configs
            return wrapped(*args, **kwargs)

        wrapt.wrap_function_wrapper(
            aiohttp.ClientSession, "__init__", instrumented_init
        )

        # requests
        wrapped_send = Session.send

        @functools.wraps(wrapped_send)
        def instrumented_send(self, request: PreparedRequest, **kwargs):
            if True:  # TODO: check DIAL URL
                api_key_val = self.dial_api_key.get()
                authorization_val = self.dial_authorization.get()

                if api_key_val:
                    request.headers["api-key"] = api_key_val
                if authorization_val:
                    request.headers["authorization"] = authorization_val

            return wrapped_send(self, request, **kwargs)

        Session.dial_api_key = self.api_key  # type: ignore
        Session.dial_authorization = self.authorization  # type: ignore
        Session.send = instrumented_send

    async def on_request_start(
        self,
        unused_session: aiohttp.ClientSession,
        trace_config_ctx: types.SimpleNamespace,
        params: aiohttp.TraceRequestStartParams,
    ):
        if not str(params.url).startswith(self._dial_url):
            return

        api_key_val = self.api_key.get()
        authorization_val = self.authorization.get()

        if api_key_val:
            params.headers["api-key"] = api_key_val
        if authorization_val:
            params.headers["authorization"] = authorization_val
