from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

from openai.types.chat import ChatCompletion, ChatCompletionChunk

from aidial_sdk.chat_completion.base import ChatCompletion as SdkChatCompletion
from aidial_sdk.chat_completion.chunks import BaseChunkWithDefaults
from aidial_sdk.chat_completion.request import Request as ChatCompletionRequest
from aidial_sdk.chat_completion.response import (
    Response as ChatCompletionResponse,
)
from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.translators._messages.sse_stream import HEARTBEAT, Heartbeat
from aidial_sdk.translators.messages_to_chat_completions.backend.client import (
    Headers,
)
from aidial_sdk.utils.streaming import (
    ResponseStream,
    merge_response_stream,
    start_streaming,
)


def _to_openai_chunk(chunk: BaseChunkWithDefaults) -> ChatCompletionChunk:
    return ChatCompletionChunk.model_validate(chunk.to_dict(with_defaults=True))


async def _to_openai_chunks(
    items: AsyncIterator[BaseChunkWithDefaults | DIALException | Heartbeat],
) -> AsyncGenerator[ChatCompletionChunk | Heartbeat, None]:
    async for item in items:
        if isinstance(item, DIALException):
            raise item
        yield item if isinstance(item, Heartbeat) else _to_openai_chunk(item)


@dataclass
class ChatClientSdk:
    parse_request: Callable[[dict], Awaitable[ChatCompletionRequest]]
    impl: SdkChatCompletion
    heartbeat_interval: float | None

    async def _generate(
        self, body: dict
    ) -> tuple[ChatCompletionResponse, ResponseStream]:
        response = ChatCompletionResponse(await self.parse_request(body))
        return response, response._generate_stream(self.impl.chat_completion)

    async def create_stream(
        self, body: dict
    ) -> tuple[AsyncGenerator[ChatCompletionChunk | Heartbeat, None], Headers]:
        response, stream = await self._generate(body)

        items = await start_streaming(
            stream,
            heartbeat_interval=self.heartbeat_interval,
            heartbeat=HEARTBEAT,
        )

        # As on the OpenAI route, the headers the impl appends after the first
        # chunk or heartbeat are lost
        return _to_openai_chunks(items), response.headers

    async def create_block(self, body: dict) -> tuple[ChatCompletion, Headers]:
        response, stream = await self._generate(body)
        response_json = await merge_response_stream(stream)
        return ChatCompletion.model_validate(response_json), response.headers
