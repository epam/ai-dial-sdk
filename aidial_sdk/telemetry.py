from contextvars import ContextVar
from typing import Optional

import aiohttp
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.aiohttp_client import (
    AioHttpClientInstrumentor,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor, Span
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from requests import PreparedRequest


class Telemetry:
    _dial_url: Optional[str]

    def __init__(
        self, app: FastAPI, dial_url: Optional[str], pass_auth_headers: bool
    ):
        self._dial_url = dial_url

        resource = Resource(attributes={SERVICE_NAME: "dial-application"})

        provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(provider)

        self.api_key: ContextVar[Optional[str]] = ContextVar(
            "api_key", default=None
        )
        self.authorization: ContextVar[Optional[str]] = ContextVar(
            "authorization", default=None
        )

        if pass_auth_headers:
            FastAPIInstrumentor.instrument_app(
                app, server_request_hook=self.server_request_hook
            )
            AioHttpClientInstrumentor().instrument(
                request_hook=self.aiohttp_request_hook
            )
            RequestsInstrumentor().instrument(
                request_hook=self.requests_request_hook
            )

    def aiohttp_request_hook(
        self, span: Span, params: aiohttp.TraceRequestStartParams
    ):
        if f"{params.url.scheme}://{params.url.host}" != self._dial_url:
            return

        api_key_val = self.api_key.get()
        authorization_val = self.authorization.get()

        if api_key_val:
            params.headers.add("api-key", api_key_val)
        if authorization_val:
            params.headers.add("authorization", authorization_val)

    def requests_request_hook(self, span: Span, request: PreparedRequest):
        # TODO: check url

        api_key_val = self.api_key.get()
        authorization_val = self.authorization.get()

        if api_key_val:
            request.headers["api-key"] = api_key_val
        if authorization_val:
            request.headers["authorization"] = authorization_val

    def server_request_hook(self, span: Span, scope: dict):
        for header in scope["headers"]:
            if header[0] == b"api-key":
                self.api_key.set(header[1].decode("utf-8"))
            elif header[0] == b"authorization":
                self.authorization.set(header[1].decode("utf-8"))
