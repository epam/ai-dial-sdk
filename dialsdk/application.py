from fastapi import FastAPI, Request
from dialsdk.assistants import ChatCompletion
from typing import Mapping
from dialsdk.chunk_stream import ChunkStream
from fastapi.responses import StreamingResponse, JSONResponse
from dialsdk.chat_completion.request import ChatCompletionRequest
from dialsdk.utils.streaming import generate_stream, merge_chunks
from json import JSONDecodeError


class DIALApp(FastAPI):
    chat_completion_impls: Mapping[str, ChatCompletion] = {}

    def __init__(self):
        super().__init__()

        self.add_api_route(
            "/openai/deployments/{deployment_id}/chat/completions",
            self.__chat_completion,
            methods=["POST"],
        )

    def add_chat_completion(self, deployment_name: str, impl: ChatCompletion):
        self.chat_completion_impls[deployment_name] = impl

    async def __chat_completion(self, deployment_id: str, original_request: Request):
        impl = self.chat_completion_impls.get(deployment_id, None)

        try:
            body = await original_request.json()
        except JSONDecodeError as e:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "message": "Your request contained invalid JSON: " + str(e),
                        "type": "invalid_request_error",
                        "param": None,
                        "code": None,
                    }
                },
            )

        headers = original_request.headers
        request = ChatCompletionRequest(
            **body,
            api_key=headers["Api-Key"],
            jwt=headers["Authorization"],
            deployment_id=deployment_id
        )

        user_task, queue, first_chunk = await ChunkStream().generator(
            impl.chat_completion, request
        )

        response_id = first_chunk.response_id
        model = first_chunk.model
        created = first_chunk.created

        chunk_stream = generate_stream(
            user_task, queue, request, response_id, model, created
        )

        if request.stream:
            return StreamingResponse(chunk_stream, media_type="text/event-stream")
        else:
            return await merge_chunks(chunk_stream, response_id, model, created)
