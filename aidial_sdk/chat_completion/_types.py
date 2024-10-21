import asyncio
from typing import TYPE_CHECKING, Union

from aidial_sdk.chat_completion.chunks import (
    BaseChunk,
    EndChunk,
    ExceptionChunk,
)

if TYPE_CHECKING:
    ChunkQueue = asyncio.Queue[Union[BaseChunk, ExceptionChunk, EndChunk]]
else:
    ChunkQueue = asyncio.Queue
