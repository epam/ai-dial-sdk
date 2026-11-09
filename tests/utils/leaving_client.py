import asyncio
import contextlib
import json

from starlette.requests import ClientDisconnect
from starlette.types import ASGIApp, Message


async def serve_to_a_leaving_client(
    app: ASGIApp, path: str, body: dict, headers: dict[str, str]
) -> None:
    """Serves a POST request to a client that leaves after the first chunk
    of the response body: the next `send` fails, the way it does on a closed
    connection under the ASGI spec 2.4."""

    received = False
    sent_chunk = False

    async def receive() -> Message:
        nonlocal received
        if received:
            # The client sends nothing more
            await asyncio.Event().wait()
        received = True
        return {
            "type": "http.request",
            "body": json.dumps(body).encode(),
            "more_body": False,
        }

    async def send(message: Message) -> None:
        nonlocal sent_chunk
        if message["type"] == "http.response.body" and message.get("body"):
            if sent_chunk:
                raise OSError("The client has left")
            sent_chunk = True

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (name.lower().encode(), value.encode())
            for name, value in {
                "content-type": "application/json",
                **headers,
            }.items()
        ],
        "client": ("client", 1234),
        "server": ("server", 80),
    }
    with contextlib.suppress(ClientDisconnect):
        await app(scope, receive, send)
