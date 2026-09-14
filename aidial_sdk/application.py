import logging
import re
import warnings
from collections.abc import Callable, Coroutine, Iterator
from typing import Any, Literal, TypeVar

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from aidial_sdk._errors import (
    dial_exception_handler,
    fastapi_exception_handler,
    pydantic_validation_exception_handler,
)
from aidial_sdk._pydantic import ValidationError
from aidial_sdk._pydantic._compat import BaseModel
from aidial_sdk.chat_completion.base import ChatCompletion
from aidial_sdk.chat_completion.request import Request as ChatCompletionRequest
from aidial_sdk.chat_completion.response import (
    Response as ChatCompletionResponse,
)
from aidial_sdk.deployment.configuration import ConfigurationRequest
from aidial_sdk.deployment.from_request_mixin import (
    FromRequestMixin,
    resolve_deployment_id,
)
from aidial_sdk.deployment.rate import RateRequest
from aidial_sdk.deployment.tokenize import TokenizeRequest
from aidial_sdk.deployment.truncate_prompt import TruncatePromptRequest
from aidial_sdk.embeddings.base import Embeddings
from aidial_sdk.embeddings.request import Request as EmbeddingsRequest
from aidial_sdk.exceptions import DeploymentNotFoundError
from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.header_propagator import HeaderPropagator
from aidial_sdk.telemetry.types import TelemetryConfig
from aidial_sdk.utils._disconnect_middleware import DisconnectMiddleware
from aidial_sdk.utils._reflection import get_method_implementation
from aidial_sdk.utils.env import env_float, env_var_list
from aidial_sdk.utils.log_config import configure_sdk_logger
from aidial_sdk.utils.logging import log_debug, set_log_deployment
from aidial_sdk.utils.pydantic import model_validate_extra_fields
from aidial_sdk.utils.streaming import (
    add_heartbeat,
    to_block_response,
    to_streaming_response,
)

configure_sdk_logger()

RequestType = TypeVar("RequestType", bound=FromRequestMixin)

Handler = Callable[[Request], Coroutine[Any, Any, Response]]


def _interpolate_deployment_id(deployment_id: str, path_params: dict) -> str:
    result = deployment_id
    for key, value in path_params.items():
        # Replace {key} or {key:type} patterns with actual value
        # Pattern matches {key} or {key:int}, {key:path}, etc.
        pattern = r"\{" + re.escape(key) + r"(?::[^}]*)?\}"
        result = re.sub(pattern, str(value), result)
    return result


class PathFilter(logging.Filter):
    path: str

    def __init__(self, path: str) -> None:
        super().__init__(name="")
        self.path = path

    def filter(self, record: logging.LogRecord):
        return not re.search(f"(\\s+){self.path}(\\s+)", record.getMessage())


class DIALApp(FastAPI):
    _allow_extra_request_fields: bool
    _dial_url: str | None
    _v1_handlers: dict[str, dict[str, Handler]]

    def __init__(
        self,
        dial_url: str | None = None,
        propagate_auth_headers: bool = False,
        telemetry_config: TelemetryConfig | None = None,
        add_healthcheck: bool = False,
        *,
        allow_extra_request_fields: bool = False,
        headers_to_proxy: list[str] | None = None,
        **kwargs,
    ):
        if "propagation_auth_headers" in kwargs:
            warnings.warn(
                "The 'propagation_auth_headers' parameter is deprecated. "
                "Use 'propagate_auth_headers' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            propagate_auth_headers = kwargs.pop("propagation_auth_headers")

        super().__init__(**kwargs)

        self._allow_extra_request_fields = allow_extra_request_fields
        self._dial_url = dial_url
        self._v1_handlers = {}

        self.configure_telemetry(telemetry_config)

        headers_to_proxy = headers_to_proxy or []
        headers_to_proxy.extend(env_var_list("DIAL_SDK_HEADERS_TO_PROXY"))

        if propagate_auth_headers or headers_to_proxy:
            if not dial_url:
                raise ValueError(
                    "dial_url is required if propagation of headers is enabled"
                )

            HeaderPropagator(
                self,
                dial_url=dial_url,
                proxy_auth_headers=propagate_auth_headers,
                headers_to_proxy=headers_to_proxy,
            ).enable()

        if add_healthcheck:
            path = "/health"
            self.add_api_route(path, DIALApp._healthcheck, methods=["GET"])
            logging.getLogger("uvicorn.access").addFilter(PathFilter(path))

        self.add_middleware(DisconnectMiddleware)

        self.add_exception_handler(
            ValidationError, pydantic_validation_exception_handler
        )

        self.add_exception_handler(HTTPException, fastapi_exception_handler)

        self.add_exception_handler(DIALException, dial_exception_handler)

    def configure_telemetry(self, config: TelemetryConfig | None):
        if config is None or config.is_noop():
            return

        try:
            from aidial_sdk.telemetry.init import init_telemetry

            init_telemetry(app=self, config=config)
        except ImportError:
            raise ValueError(
                "Missing telemetry dependencies. "
                "Install the package with the extras: aidial-sdk[telemetry]"
            )

    def add_embeddings(
        self, deployment_name: str, impl: Embeddings
    ) -> "DIALApp":
        self.add_api_route(
            f"/openai/deployments/{deployment_name}/embeddings",
            self._embeddings(deployment_name, impl),
            methods=["POST"],
        )

        self._add_v1_route(
            deployment_name,
            "embeddings",
            self._embeddings(None, impl),
            methods=["POST"],
        )

        return self

    def add_chat_completion(
        self,
        deployment_name: str,
        impl: ChatCompletion,
        *,
        heartbeat_interval: float | None = None,
    ) -> "DIALApp":
        for endpoint, handler, methods in self._chat_completion_handlers(
            deployment_name, impl, heartbeat_interval
        ):
            self.add_api_route(
                f"/openai/deployments/{deployment_name}/{endpoint}",
                handler,
                methods=methods,
            )

        for endpoint, handler, methods in self._chat_completion_handlers(
            None, impl, heartbeat_interval
        ):
            self._add_v1_route(
                deployment_name, endpoint, handler, methods=methods
            )

        return self

    def _chat_completion_handlers(
        self,
        deployment_id: str | None,
        impl: ChatCompletion,
        heartbeat_interval: float | None,
    ) -> Iterator[tuple[str, Handler, list[str]]]:
        yield (
            "chat/completions",
            self._chat_completion(
                deployment_id, impl, heartbeat_interval=heartbeat_interval
            ),
            ["POST"],
        )

        yield "rate", self._rate_response(deployment_id, impl), ["POST"]

        if endpoint_impl := get_method_implementation(impl, "tokenize"):
            yield (
                "tokenize",
                self._endpoint_factory(
                    deployment_id, endpoint_impl, "tokenize", TokenizeRequest
                ),
                ["POST"],
            )

        if endpoint_impl := get_method_implementation(impl, "truncate_prompt"):
            yield (
                "truncate_prompt",
                self._endpoint_factory(
                    deployment_id,
                    endpoint_impl,
                    "truncate_prompt",
                    TruncatePromptRequest,
                ),
                ["POST"],
            )

        if endpoint_impl := get_method_implementation(impl, "configuration"):
            yield (
                "configuration",
                self._endpoint_factory(
                    deployment_id,
                    endpoint_impl,
                    "configuration",
                    ConfigurationRequest,
                ),
                ["GET"],
            )

    def _add_v1_route(
        self,
        deployment_name: str,
        endpoint: str,
        handler: Handler,
        *,
        methods: list[str],
    ) -> None:
        """The /openai/v1 endpoints are shared by all the deployments of
        the application, so they are dispatched by the deployment id
        resolved from the request headers."""

        if endpoint not in self._v1_handlers:
            self._v1_handlers[endpoint] = {}
            self.add_api_route(
                f"/openai/v1/{endpoint}",
                self._v1_dispatcher(endpoint),
                methods=methods,
            )

        self._v1_handlers[endpoint][deployment_name] = handler

    def _v1_dispatcher(self, endpoint: str) -> Handler:
        async def _handler(original_request: Request) -> Response:
            deployment_id = resolve_deployment_id(
                original_request.headers, None
            )
            set_log_deployment(deployment_id)

            handler = self._v1_handlers[endpoint].get(deployment_id)
            if handler is None:
                raise DeploymentNotFoundError(
                    f"The deployment {deployment_id!r} doesn't provide the {endpoint!r} endpoint"
                )

            return await handler(original_request)

        return _handler

    def _endpoint_factory(
        self,
        deployment_id: str | None,
        endpoint_impl: Callable[[RequestType], Coroutine[Any, Any, Any]],
        endpoint: Literal["tokenize", "truncate_prompt", "configuration"],
        request_type: type["RequestType"],
    ):
        async def _handler(original_request: Request) -> Response:
            request = await self._parse_request(
                request_type, original_request, deployment_id
            )
            log_debug(f"request[{endpoint}]: {request}")

            response = await endpoint_impl(request)

            if isinstance(response, dict):
                response_json = response
            elif isinstance(response, BaseModel):
                response_json = response.model_dump()
            else:
                raise ValueError(
                    f"Unexpected response type from {endpoint}: {type(response)}"
                )

            log_debug(f"response[{endpoint}]: {response_json}")

            return JSONResponse(content=response_json)

        return _handler

    def _rate_response(self, deployment_id: str | None, impl: ChatCompletion):
        async def _handler(original_request: Request):
            request = await self._parse_request(
                RateRequest, original_request, deployment_id
            )

            await impl.rate_response(request)
            return Response(status_code=200)

        return _handler

    async def _parse_request(
        self,
        request: type[RequestType],
        original_request: Request,
        deployment_id: str | None,
    ) -> RequestType:
        if deployment_id is not None:
            deployment_id = _interpolate_deployment_id(
                deployment_id, original_request.path_params
            )
            set_log_deployment(deployment_id)

        ret = await request.from_request(
            original_request, deployment_id, self._dial_url
        )
        if not self._allow_extra_request_fields:
            model_validate_extra_fields(ret)
        return ret

    def _chat_completion(
        self,
        deployment_id: str | None,
        impl: ChatCompletion,
        *,
        heartbeat_interval: float | None,
    ):
        heartbeat_interval = heartbeat_interval or env_float(
            "DIAL_SDK_SSE_HEARTBEAT_INTERVAL"
        )

        async def _handler(original_request: Request) -> Response:
            request = await self._parse_request(
                ChatCompletionRequest, original_request, deployment_id
            )

            response = ChatCompletionResponse(request)

            stream = response._generate_stream(impl.chat_completion)

            if request.stream:
                if heartbeat_interval:
                    stream = add_heartbeat(
                        stream,
                        heartbeat_interval=heartbeat_interval,
                        heartbeat_callback=lambda: log_debug("heartbeat"),
                        heartbeat_object=": heartbeat\n\n",
                    )

                resp = StreamingResponse(
                    await to_streaming_response(stream),
                    media_type="text/event-stream",
                )
            else:
                response_json = await to_block_response(stream)
                log_debug(f"response: {response_json}")
                resp = JSONResponse(content=response_json)

            for key, value in response.headers:
                resp.headers.append(key, value)

            return resp

        return _handler

    def _embeddings(self, deployment_id: str | None, impl: Embeddings):
        async def _handler(original_request: Request):
            request = await self._parse_request(
                EmbeddingsRequest, original_request, deployment_id
            )
            response = await impl.embeddings(request)
            response_json = response.model_dump()
            return JSONResponse(content=response_json)

        return _handler

    @staticmethod
    async def _healthcheck() -> JSONResponse:
        return JSONResponse(content={"status": "ok"})
