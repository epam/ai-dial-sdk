import asyncio
from typing import Any, MutableMapping

from aidial_sdk.utils.logging import log_error

Scope = MutableMapping[str, Any]


def log_client_disconnect(scope: Scope) -> None:
    client = (
        f"{scope['client'][0]}:{scope['client'][1]}"
        if scope.get("client")
        else "-:-"
    )
    method = scope.get("method", "-")
    path = scope.get("path", "-")

    log_error(
        '%s - "%s %s" 499 DISCONNECTED',
        client,
        method,
        path,
    )


class DisconnectMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        queue = asyncio.Queue()
        response_completed = False
        response_started = False

        async def message_poller(sentinel, handler_task):
            nonlocal queue
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    # Only cancel if response hasn't completed (premature disconnect)
                    if not response_completed:
                        handler_task.cancel()
                        return sentinel
                    # If response completed, this is normal - don't cancel
                    return sentinel
                await queue.put(message)

        async def send_wrapper(response):
            nonlocal response_started, response_completed
            if response["type"] == "http.response.start":
                response_started = True
            elif response["type"] == "http.response.body":
                if not response.get("more_body", False):
                    response_completed = True  # Response sent
            await send(response)

        sentinel = object()
        handler_task = asyncio.create_task(
            self.app(scope, queue.get, send_wrapper)
        )
        poller_task = asyncio.create_task(
            message_poller(sentinel, handler_task)
        )

        try:
            return await handler_task
        except asyncio.CancelledError:
            log_client_disconnect(scope)
        finally:
            if not poller_task.done():
                poller_task.cancel()
                try:
                    await poller_task
                except asyncio.CancelledError:
                    pass
