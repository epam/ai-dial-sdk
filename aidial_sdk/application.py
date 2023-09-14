import logging.config
from json import JSONDecodeError
from typing import Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from aidial_sdk.chat_completion.chat_completion import ChatCompletion
from aidial_sdk.chat_completion.request import ChatCompletionRequest
from aidial_sdk.chat_completion.response import ChatCompletionResponse
from aidial_sdk.header_propagation import HeaderPropogetaion
from aidial_sdk.utils.log_config import LogConfig
from aidial_sdk.utils.streaming import json_error, merge_chunks

logging.config.dictConfig(LogConfig().dict())


class DIALApp(FastAPI):
    chat_completion_impls: Dict[str, ChatCompletion] = {}

    def __init__(
        self,
        dial_url: Optional[str] = None,
        propagation_auth_headers: bool = False,
    ):
        super().__init__()

        if propagation_auth_headers:
            if not dial_url:
                raise ValueError(
                    "dial_url is required if propagation auth headers is enabled"
                )

            HeaderPropogetaion(self, dial_url)

        self.add_api_route(
            "/openai/deployments/{deployment_id}/chat/completions",
            self._chat_completion,
            methods=["POST"],
        )

    def add_chat_completion(
        self, deployment_name: str, impl: ChatCompletion
    ) -> None:
        self.chat_completion_impls[deployment_name] = impl

    async def _chat_completion(
        self, deployment_id: str, original_request: Request
    ) -> Response:
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
                    message="Your request contained invalid JSON: " + str(e),
                    type="invalid_request_error",
                ),
            )

        headers = original_request.headers
        request = ChatCompletionRequest(
            **body,
            api_key=headers["Api-Key"],
            jwt=headers.get("Authorization"),
            deployment_id=deployment_id,
        )

        deployment_logger = logging.getLogger(deployment_id)
        deployment_logger.debug(f"Request body: {body}")

        response = ChatCompletionResponse(request)
        await response._generator(impl.chat_completion, request)

        if request.stream:
            return StreamingResponse(
                response._generate_stream(), media_type="text/event-stream"
            )
        else:
            response_body = await merge_chunks(response._generate_stream())

            deployment_logger.debug(f"Response body: {response_body}")
            return JSONResponse(content=response_body)
