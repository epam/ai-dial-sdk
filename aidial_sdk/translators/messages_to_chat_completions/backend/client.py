from collections.abc import AsyncGenerator
from typing import Protocol

from openai.types.chat import ChatCompletion, ChatCompletionChunk

Headers = list[tuple[str, str]]


class Heartbeat:
    """Yielded by a chat stream for each heartbeat interval it was idle."""


HEARTBEAT = Heartbeat()


class ChatClient(Protocol):
    async def create_stream(
        self, body: dict
    ) -> tuple[
        AsyncGenerator[ChatCompletionChunk | Heartbeat, None], Headers
    ]: ...

    async def create_block(
        self, body: dict
    ) -> tuple[ChatCompletion, Headers]: ...
