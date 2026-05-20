import asyncio
from typing import TYPE_CHECKING

from aidial_sdk.chat_completion.chunks import (
    BaseChunk,
    EndChunk,
    ExceptionChunk,
)

if TYPE_CHECKING:
    ChunkQueue = asyncio.Queue[BaseChunk | ExceptionChunk | EndChunk]
else:
    ChunkQueue = asyncio.Queue
