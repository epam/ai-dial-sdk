import logging.config
from json import JSONDecodeError
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from aidial_sdk.chat_completion.base import ChatCompletion
from aidial_sdk.chat_completion.request import Request as ChatCompletionRequest
from aidial_sdk.chat_completion.response import (
    Response as ChatCompletionResponse,
)
from aidial_sdk.header_propagator import HeaderPropagator
from aidial_sdk.pydantic_v1 import ValidationError
from aidial_sdk.telemetry import TelemetryConfig
from aidial_sdk.utils.errors import json_error
from aidial_sdk.utils.log_config import LogConfig
from aidial_sdk.utils.logging import log_debug, set_log_deployment
from aidial_sdk.utils.streaming import merge_chunks

logging.config.dictConfig(LogConfig().dict())


class DIALApp(FastAPI):
    chat_completion_impls: Dict[str, ChatCompletion] = {}

    def __init__(
        self,
        dial_url: Optional[str] = None,
        propagation_auth_headers: bool = False,
        telemetry_config: Optional[TelemetryConfig] = None,
        **fast_api_kwargs,
    ):
        super().__init__(**fast_api_kwargs)

        if telemetry_config is not None:
            self.configure_telemetry(telemetry_config)

        if propagation_auth_headers:
            if not dial_url:
                raise ValueError(
                    "dial_url is required if propagation auth headers is enabled"
                )

            HeaderPropagator(self, dial_url).enable()

        self.add_api_route(
            "/openai/deployments/{deployment_id}/chat/completions",
            self._chat_completion,
            methods=["POST"],
        )

        self.add_exception_handler(HTTPException, DIALApp._exception_handler)

    def configure_telemetry(self, config: TelemetryConfig):
        try:
            from aidial_sdk.telemetry import init_telemetry
        except ImportError:
            raise ValueError(
                "Missing telemetry dependencies. "
                "Install the package with the extras: aidial-sdk[telemetry]"
            )

        init_telemetry(app=self, config=config)

    def add_chat_completion(
        self, deployment_name: str, impl: ChatCompletion
    ) -> None:
        self.chat_completion_impls[deployment_name] = impl

    async def _chat_completion(
        self, deployment_id: str, original_request: Request
    ) -> Response:
        set_log_deployment(deployment_id)
        impl = self.chat_completion_impls.get(deployment_id, None)

        if not impl:
            return JSONResponse(
                status_code=404,
                content=json_error(
                    message="The API deployment for this resource does not exist.",
                    code="deployment_not_found",
                ),
            )

        try:
            body = await original_request.json()
        except JSONDecodeError as e:
            return JSONResponse(
                status_code=400,
                content=json_error(
                    message=f"Your request contained invalid JSON: {str(e)}",
                    type="invalid_request_error",
                ),
            )

        headers = original_request.headers
        try:
            request = ChatCompletionRequest(
                **body,
                api_key=headers["Api-Key"],
                jwt=headers.get("Authorization"),
                deployment_id=deployment_id,
                api_version=original_request.query_params.get("api-version"),
                headers=headers,
            )
        except ValidationError as e:
            error = e.errors()[0]
            path = ".".join(map(str, e.errors()[0]["loc"]))
            return JSONResponse(
                status_code=400,
                content=json_error(
                    message=f"Your request contained invalid structure on path {path}. {error['msg']}",
                    type="invalid_request_error",
                ),
            )

        log_debug(f"request: {body}")

        response = ChatCompletionResponse(request)
        first_chunk = await response._generator(impl.chat_completion, request)

        if request.stream:
            return StreamingResponse(
                response._generate_stream(first_chunk),
                media_type="text/event-stream",
            )
        else:
            response_body = await merge_chunks(
                response._generate_stream(first_chunk)
            )

            log_debug(f"response: {response_body}")
            return JSONResponse(content=response_body)

    @staticmethod
    def _exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )
