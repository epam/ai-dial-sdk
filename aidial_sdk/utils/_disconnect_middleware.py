import asyncio
import contextlib
from collections.abc import MutableMapping
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

from aidial_sdk.utils.logging import log_error


def _log_client_disconnect(scope: Scope) -> None:
    client = scope.get("client", ("-", "-"))
    method = scope.get("method", "-")
    path = scope.get("path", "-")
    log_error(
        f'{client[0]}:{client[1]} - "{method} {path}" Client disconnected'
    )


class DisconnectMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        queue: asyncio.Queue = asyncio.Queue()
        response_completed = False

        async def message_poller(handler_task: asyncio.Task) -> None:
            while True:
                message = await receive()
                await queue.put(message)
                if message["type"] == "http.disconnect":
                    # Only cancel if response hasn't completed (premature disconnect)
                    if not response_completed:
                        handler_task.cancel()
                    return

        async def send_wrapper(response: MutableMapping[str, Any]) -> None:
            nonlocal response_completed
            if response["type"] == "http.response.body" and not response.get(
                "more_body", False
            ):
                response_completed = True
            await send(response)

        async def run_app() -> None:
            await self.app(scope, queue.get, send_wrapper)

        handler_task = asyncio.create_task(run_app())
        poller_task = asyncio.create_task(message_poller(handler_task))

        try:
            await handler_task
        except asyncio.CancelledError:
            _log_client_disconnect(scope)
        finally:
            if not poller_task.done():
                poller_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await poller_task
