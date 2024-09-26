from typing import Protocol

from aidial_sdk.chat_completion.chunks import BaseChunk


class ChunkConsumer(Protocol):
    def send_chunk(self, chunk: BaseChunk): ...
