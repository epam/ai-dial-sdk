from collections.abc import AsyncGenerator
from typing import Protocol

from openai.types.chat import ChatCompletion, ChatCompletionChunk

from aidial_sdk.translators._messages.sse_stream import Heartbeat

Headers = list[tuple[str, str]]


class ChatClient(Protocol):
    async def create_stream(
        self, body: dict
    ) -> tuple[
        AsyncGenerator[ChatCompletionChunk | Heartbeat, None], Headers
    ]: ...

    async def create_block(
        self, body: dict
    ) -> tuple[ChatCompletion, Headers]: ...
