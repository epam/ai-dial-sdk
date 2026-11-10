import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi.responses import StreamingResponse
from starlette.responses import ContentStream
from starlette.types import Receive, Scope, Send


class ClosingStreamingResponse(StreamingResponse):
    """Calls `close` however the response ends: when the client leaves,
    Starlette leaves the content suspended, and with it whatever the content
    holds, until the garbage collector finalizes it."""

    def __init__(
        self,
        content: ContentStream,
        close: Callable[[], Awaitable[None]],
        **kwargs: Any,
    ) -> None:
        super().__init__(content, **kwargs)
        self._close = close

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            # Shielded: the task may be the one cancelled
            await asyncio.shield(self._close())
