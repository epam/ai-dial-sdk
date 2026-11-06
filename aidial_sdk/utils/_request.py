import json
from collections.abc import Mapping

from fastapi import Request
from starlette.types import Message


def with_json_body(request: Request, body: Mapping[str, object]) -> Request:
    data = json.dumps(body).encode()
    headers = [
        (key, value)
        for key, value in request.scope["headers"]
        if key != b"content-length"
    ]
    headers.append((b"content-length", str(len(data)).encode()))

    async def receive() -> Message:
        return {"type": "http.request", "body": data, "more_body": False}

    return Request({**request.scope, "headers": headers}, receive)
