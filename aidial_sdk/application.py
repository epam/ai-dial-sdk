from json import JSONDecodeError
from typing import Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from aidial_sdk.assistants import ChatCompletion
from aidial_sdk.chat_completion.request import ChatCompletionRequest
from aidial_sdk.chat_completion.response import ChatCompletionResponse
from aidial_sdk.utils.streaming import merge_chunks


def json_error(
    message: Optional[str] = None,
    type: Optional[str] = None,
    param: Optional[str] = None,
    code: Optional[str] = None,
):
    return {
        "error": {
            "message": message,
            "type": type,
            "param": param,
            "code": code,
        }
    }


class DIALApp(FastAPI):
    chat_completion_impls: Dict[str, ChatCompletion] = {}

    def __init__(self):
        super().__init__()

        self.add_api_route(
            "/openai/deployments/{deployment_id}/chat/completions",
            self.__chat_completion,
            methods=["POST"],
        )

    def add_chat_completion(
        self, deployment_name: str, impl: ChatCompletion
    ) -> None:
        self.chat_completion_impls[deployment_name] = impl

    async def __chat_completion(
        self, deployment_id: str, original_request: Request
    ) -> Response:
        impl = self.chat_completion_impls[deployment_id]

        if not impl:
            return JSONResponse(
                status_code=404,
                content=json_error(
                    message="The API deployment for this resource does not exist.",
                    code="DeploymentNotFound",
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
            jwt=headers.get("Authorization", ""),
            deployment_id=deployment_id
        )

        response = ChatCompletionResponse(request)
        await response._generator(impl.chat_completion, request)

        if request.stream:
            return StreamingResponse(
                response._generate_stream(), media_type="text/event-stream"
            )
        else:
            return await merge_chunks(response._generate_stream())
