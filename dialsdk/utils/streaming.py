import asyncio
import json
from dialsdk.chunk_stream import ChunkStream
from dialsdk.chat_completion.request import ChatCompletionRequest
from dialsdk.utils.merge_chunks import merge_recursive
from dialsdk.chat_completion.chunks import (
    DIALChatCompletionEndChoiceChunk,
    DIALChatCompletionUsageChunk,
    DIALChatCompletionBaseChunk,
    DIALChatCompletionEndChunk,
)


def add_default_fields(target, response_id, model, created, type):
    target["id"] = response_id
    if model:
        target["model"] = model
    target["created"] = created
    target["object"] = type


async def generate_stream(
    user_task,
    queue: asyncio.Queue,
    request: ChatCompletionRequest,
    response_id: str,
    model: str,
    created: int,
):
    last_end_choice_chunk = None
    while True:
        get_task = asyncio.create_task(queue.get())
        done, pending = await asyncio.wait(
            [get_task, user_task], return_when=asyncio.FIRST_COMPLETED
        )
        if user_task in done:
            user_task.result()
        item = get_task.result() if get_task in done else await get_task

        if isinstance(item, DIALChatCompletionEndChoiceChunk):
            if item.index == request.n - 1:
                last_end_choice_chunk = item
                continue

        if isinstance(item, DIALChatCompletionUsageChunk):
            chunk = merge_recursive(
                last_end_choice_chunk.to_dict(), item.to_dict(), path=[]
            )

            if request.stream:
                add_default_fields(
                    chunk,
                    response_id,
                    model,
                    created,
                    "chat.completion.chunk",
                )
                yield generate_chunk(chunk)
            else:
                yield chunk
        elif isinstance(item, DIALChatCompletionBaseChunk):
            chunk = item.to_dict()

            if request.stream:
                add_default_fields(
                    chunk,
                    response_id,
                    model,
                    created,
                    "chat.completion.chunk",
                )
                yield generate_chunk(chunk)
            else:
                yield chunk
        elif isinstance(item, DIALChatCompletionEndChunk):
            if request.stream:
                yield "data: [DONE]\n"
            return


async def merge_chunks(chunk_stream, response_id, model, created):
    response = None
    async for chunk in chunk_stream:
        if response == None:
            response = chunk
        else:
            print(chunk)
            response["choices"] = merge_recursive(
                response["choices"], chunk["choices"], []
            )

        statistics = chunk.get("statistics", None)
        if statistics:
            if response.get("statistics", None) == None:
                response["statistics"] = statistics
            else:
                response["statistics"] = merge_recursive(
                    response["statistics"], statistics, []
                )

        if chunk["usage"]:
            response["usage"] = chunk["usage"]

    for choice in response["choices"]:
        choice["message"] = choice["delta"]
        del choice["delta"]

    add_default_fields(response, response_id, model, created, "chat.completion")

    return response


def generate_chunk(data):
    return "data: " + json.dumps(data, separators=(",", ":")) + "\n\n"
