import logging.config
import re
import warnings
from logging import Filter, LogRecord
from typing import Dict, Optional, Type, TypeVar

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from aidial_sdk._errors import (
    dial_exception_handler,
    fastapi_exception_handler,
    missing_deployment_error,
    missing_endpoint_error,
    pydantic_validation_exception_handler,
)
from aidial_sdk.chat_completion.base import ChatCompletion
from aidial_sdk.chat_completion.request import Request as ChatCompletionRequest
from aidial_sdk.chat_completion.response import (
    Response as ChatCompletionResponse,
)
from aidial_sdk.deployment.from_request_mixin import FromRequestMixin
from aidial_sdk.deployment.rate import RateRequest
from aidial_sdk.deployment.tokenize import TokenizeRequest
from aidial_sdk.deployment.truncate_prompt import TruncatePromptRequest
from aidial_sdk.embeddings.base import Embeddings
from aidial_sdk.embeddings.request import Request as EmbeddingsRequest
from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.header_propagator import HeaderPropagator
from aidial_sdk.pydantic_v1 import ValidationError
from aidial_sdk.telemetry.types import TelemetryConfig
from aidial_sdk.utils.log_config import LogConfig
from aidial_sdk.utils.logging import log_debug, set_log_deployment
from aidial_sdk.utils.streaming import merge_chunks

logging.config.dictConfig(LogConfig().dict())

RequestType = TypeVar("RequestType", bound=FromRequestMixin)


class PathFilter(Filter):
    path: str

    def __init__(self, path: str) -> None:
        super().__init__(name="")
        self.path = path

    def filter(self, record: LogRecord):
        return not re.search(f"(\\s+){self.path}(\\s+)", record.getMessage())


class DIALApp(FastAPI):
    chat_completion_impls: Dict[str, ChatCompletion] = {}
    embeddings_impls: Dict[str, Embeddings] = {}

    def __init__(
        self,
        dial_url: Optional[str] = None,
        propagate_auth_headers: bool = False,
        telemetry_config: Optional[TelemetryConfig] = None,
        add_healthcheck: bool = False,
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

        self.add_api_route(
            "/openai/deployments/{deployment_id}/embeddings",
            self._embeddings,
            methods=["POST"],
        )

        self.add_api_route(
            "/openai/deployments/{deployment_id}/chat/completions",
            self._chat_completion,
            methods=["POST"],
        )

        self.add_api_route(
            "/openai/deployments/{deployment_id}/rate",
            self._rate_response,
            methods=["POST"],
        )

        self.add_api_route(
            "/openai/deployments/{deployment_id}/tokenize",
            self._chat_completion_endpoint_factory("tokenize", TokenizeRequest),
            methods=["POST"],
        )

        self.add_api_route(
            "/openai/deployments/{deployment_id}/truncate_prompt",
            self._chat_completion_endpoint_factory(
                "truncate_prompt", TruncatePromptRequest
            ),
            methods=["POST"],
        )

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

    def add_embeddings(self, deployment_name: str, impl: Embeddings) -> None:
        self.embeddings_impls[deployment_name] = impl

    def add_chat_completion(
        self, deployment_name: str, impl: ChatCompletion
    ) -> None:
        self.chat_completion_impls[deployment_name] = impl

    def _chat_completion_endpoint_factory(
        self, endpoint: str, request_type: Type["RequestType"]
    ):
        async def _handler(
            deployment_id: str, original_request: Request
        ) -> Response:
            set_log_deployment(deployment_id)
            deployment = self._get_chat_completion(deployment_id)

            request = await request_type.from_request(original_request)

            endpoint_impl = getattr(deployment, endpoint, None)
            if not endpoint_impl:
                raise missing_endpoint_error(endpoint)

            try:
                response = await endpoint_impl(request)
            except NotImplementedError:
                raise missing_endpoint_error(endpoint)

            response_json = response.dict()
            log_debug(f"response [{endpoint}]: {response_json}")
            return JSONResponse(content=response_json)

        return _handler

    async def _rate_response(
        self, deployment_id: str, original_request: Request
    ) -> Response:
        set_log_deployment(deployment_id)
        deployment = self._get_chat_completion(deployment_id)

        request = await RateRequest.from_request(original_request)

        await deployment.rate_response(request)
        return Response(status_code=200)

    async def _embeddings(
        self, deployment_id: str, original_request: Request
    ) -> Response:
        set_log_deployment(deployment_id)
        deployment = self._get_embeddings(deployment_id)
        request = await EmbeddingsRequest.from_request(original_request)
        response = await deployment.embeddings(request)
        response_json = response.dict()
        return JSONResponse(content=response_json)

    async def _chat_completion(
        self, deployment_id: str, original_request: Request
    ) -> Response:
        set_log_deployment(deployment_id)
        deployment = self._get_chat_completion(deployment_id)

        request = await ChatCompletionRequest.from_request(original_request)

        response = ChatCompletionResponse(request)
        first_chunk = await response._generator(
            deployment.chat_completion, request
        )

        if request.stream:
            return StreamingResponse(
                response._generate_stream(first_chunk),
                media_type="text/event-stream",
            )
        else:
            response_json = await merge_chunks(
                response._generate_stream(first_chunk)
            )

            log_debug(f"response: {response_json}")
            return JSONResponse(content=response_json)

    @staticmethod
    async def _healthcheck() -> JSONResponse:
        return JSONResponse(content={"status": "ok"})

    def _get_chat_completion(self, deployment_id: str) -> ChatCompletion:
        impl = self.chat_completion_impls.get(deployment_id, None)
        if not impl:
            raise missing_deployment_error()
        return impl

    def _get_embeddings(self, deployment_id: str) -> Embeddings:
        impl = self.embeddings_impls.get(deployment_id, None)
        if not impl:
            raise missing_deployment_error()
        return impl
