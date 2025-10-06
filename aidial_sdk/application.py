import logging.config
import re
import warnings
from logging import Filter, LogRecord
from typing import Any, Callable, Coroutine, Literal, Optional, Type, TypeVar

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
from aidial_sdk.deployment.from_request_mixin import FromRequestMixin
from aidial_sdk.deployment.rate import RateRequest
from aidial_sdk.deployment.tokenize import TokenizeRequest
from aidial_sdk.deployment.truncate_prompt import TruncatePromptRequest
from aidial_sdk.embeddings.base import Embeddings
from aidial_sdk.embeddings.request import Request as EmbeddingsRequest
from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.header_propagator import HeaderPropagator
from aidial_sdk.telemetry.types import TelemetryConfig
from aidial_sdk.utils._reflection import get_method_implementation
from aidial_sdk.utils.log_config import LogConfig
from aidial_sdk.utils.logging import log_debug, set_log_deployment
from aidial_sdk.utils.pydantic import model_validate_extra_fields
from aidial_sdk.utils.streaming import (
    add_heartbeat,
    to_block_response,
    to_streaming_response,
)

logging.config.dictConfig(LogConfig().model_dump())

RequestType = TypeVar("RequestType", bound=FromRequestMixin)


class PathFilter(Filter):
    path: str

    def __init__(self, path: str) -> None:
        super().__init__(name="")
        self.path = path

    def filter(self, record: LogRecord):
        return not re.search(f"(\\s+){self.path}(\\s+)", record.getMessage())


class DIALApp(FastAPI):
    _allow_extra_request_fields: bool
    _dial_url: Optional[str]

    def __init__(
        self,
        dial_url: Optional[str] = None,
        propagate_auth_headers: bool = False,
        telemetry_config: Optional[TelemetryConfig] = None,
        add_healthcheck: bool = False,
        *,
        allow_extra_request_fields: bool = False,
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

        if telemetry_config is not None:
            self.configure_telemetry(telemetry_config)

        if propagate_auth_headers:
            if not dial_url:
                raise ValueError(
                    "dial_url is required if propagation auth headers is enabled"
                )

            HeaderPropagator(self, dial_url).enable()

        if add_healthcheck:
            path = "/health"
            self.add_api_route(path, DIALApp._healthcheck, methods=["GET"])
            logging.getLogger("uvicorn.access").addFilter(PathFilter(path))

        self.add_exception_handler(
            ValidationError, pydantic_validation_exception_handler
        )

        self.add_exception_handler(HTTPException, fastapi_exception_handler)

        self.add_exception_handler(DIALException, dial_exception_handler)

    def configure_telemetry(self, config: TelemetryConfig):
        try:
            from aidial_sdk.telemetry.init import init_telemetry
        except ImportError:
            raise ValueError(
                "Missing telemetry dependencies. "
                "Install the package with the extras: aidial-sdk[telemetry]"
            )

        init_telemetry(app=self, config=config)

    def add_embeddings(
        self, deployment_name: str, impl: Embeddings
    ) -> "DIALApp":
        self.add_api_route(
            f"/openai/deployments/{deployment_name}/embeddings",
            self._embeddings(deployment_name, impl),
            methods=["POST"],
        )

        return self

    def add_chat_completion(
        self,
        deployment_name: str,
        impl: ChatCompletion,
        *,
        heartbeat_interval: Optional[float] = None,
    ) -> "DIALApp":

        self.add_api_route(
            f"/openai/deployments/{deployment_name}/chat/completions",
            self._chat_completion(
                deployment_name,
                impl,
                heartbeat_interval=heartbeat_interval,
            ),
            methods=["POST"],
        )

        self.add_api_route(
            f"/openai/deployments/{deployment_name}/rate",
            self._rate_response(deployment_name, impl),
            methods=["POST"],
        )

        if endpoint_impl := get_method_implementation(impl, "tokenize"):
            self.add_api_route(
                f"/openai/deployments/{deployment_name}/tokenize",
                self._endpoint_factory(
                    deployment_name, endpoint_impl, "tokenize", TokenizeRequest
                ),
                methods=["POST"],
            )

        if endpoint_impl := get_method_implementation(impl, "truncate_prompt"):
            self.add_api_route(
                f"/openai/deployments/{deployment_name}/truncate_prompt",
                self._endpoint_factory(
                    deployment_name,
                    endpoint_impl,
                    "truncate_prompt",
                    TruncatePromptRequest,
                ),
                methods=["POST"],
            )

        if endpoint_impl := get_method_implementation(impl, "configuration"):
            self.add_api_route(
                f"/openai/deployments/{deployment_name}/configuration",
                self._endpoint_factory(
                    deployment_name,
                    endpoint_impl,
                    "configuration",
                    ConfigurationRequest,
                ),
                methods=["GET"],
            )

        return self

    def _endpoint_factory(
        self,
        deployment_id: str,
        endpoint_impl: Callable[[RequestType], Coroutine[Any, Any, Any]],
        endpoint: Literal["tokenize", "truncate_prompt", "configuration"],
        request_type: Type["RequestType"],
    ):
        async def _handler(original_request: Request) -> Response:
            set_log_deployment(deployment_id)

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

    def _rate_response(self, deployment_id: str, impl: ChatCompletion):
        async def _handler(original_request: Request):
            set_log_deployment(deployment_id)

            request = await self._parse_request(
                RateRequest, original_request, deployment_id
            )

            await impl.rate_response(request)
            return Response(status_code=200)

        return _handler

    async def _parse_request(
        self,
        request: Type[RequestType],
        original_request: Request,
        deployment_id: str,
    ) -> RequestType:
        ret = await request.from_request(
            original_request, deployment_id, self._dial_url
        )
        if not self._allow_extra_request_fields:
            model_validate_extra_fields(ret)
        return ret

    def _chat_completion(
        self,
        deployment_id: str,
        impl: ChatCompletion,
        *,
        heartbeat_interval: Optional[float],
    ):
        async def _handler(original_request: Request):
            set_log_deployment(deployment_id)

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

    def _embeddings(self, deployment_id: str, impl: Embeddings):
        async def _handler(original_request: Request):
            set_log_deployment(deployment_id)
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
