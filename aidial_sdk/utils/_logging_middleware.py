import logging

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from aidial_sdk.utils.logging import logger as log


def _as_text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def _one_line(data: bytes) -> str:
    return "".join(_as_text(data).splitlines())


_LOGGED_SCOPE_KEY = "aidial_sdk.logged"


class LoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if (
            scope["type"] != "http"
            or scope.get(_LOGGED_SCOPE_KEY)
            or not log.isEnabledFor(logging.DEBUG)
        ):
            await self.app(scope, receive, send)
            return

        # Makes the middleware of the apps mounted into this one a no-op
        scope[_LOGGED_SCOPE_KEY] = True

        request_chunks: list[bytes] = []

        async def receive_wrapper() -> Message:
            message = await receive()
            if message["type"] == "http.request":
                request_chunks.append(message.get("body", b""))
                if not message.get("more_body", False):
                    log.debug(f"request: {_one_line(b''.join(request_chunks))}")
            return message

        # A compressed body, e.g. relayed as is from an upstream, isn't text
        encoding = "identity"

        async def send_wrapper(message: Message) -> None:
            nonlocal encoding
            if message["type"] == "http.response.start":
                headers = Headers(raw=message.get("headers", []))
                encoding = headers.get("content-encoding", "identity")
            elif message["type"] == "http.response.body" and (
                body := message.get("body", b"")
            ):
                more_body = message.get("more_body", False)
                if encoding != "identity":
                    text = f"<{encoding}-encoded, {len(body)} bytes>"
                elif more_body:
                    text = _as_text(body).rstrip()
                else:
                    text = _one_line(body)
                log.debug(
                    f"response chunk: {text}"
                    if more_body
                    else f"response: {text}"
                )
            await send(message)

        await self.app(scope, receive_wrapper, send_wrapper)
