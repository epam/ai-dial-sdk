import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import Response, StreamingResponse
from fastapi.testclient import TestClient

from aidial_sdk import DIALApp
from aidial_sdk import HTTPException as DIALException
from aidial_sdk.response_headers import strip_stale_content_headers

# What an upstream response carries on top of its application headers.
UPSTREAM_HEADERS = {
    "content-type": "application/json",
    "transfer-encoding": "chunked",
    "connection": "close",
    "server": "upstream-server",
    "date": "Mon, 01 Jan 2024 00:00:00 GMT",
    "x-request-id": "req-1",
}

BODY = b'{"ok":1}'


def _create_passthrough_app() -> FastAPI:
    """An upstream proxy mounted into the DIAL app, relaying the headers."""

    app = FastAPI()

    @app.get("/block")
    async def _block() -> Response:
        return Response(content=BODY, headers=dict(UPSTREAM_HEADERS))

    @app.get("/stream")
    async def _stream() -> Response:
        async def _chunks():
            yield BODY

        return StreamingResponse(_chunks(), headers=dict(UPSTREAM_HEADERS))

    return app


@pytest.fixture
def client() -> TestClient:
    app = DIALApp()
    app.mount("/passthrough", _create_passthrough_app())

    @app.get("/error")
    async def _error() -> Response:
        raise DIALException(
            "Upstream failed", status_code=400, headers=dict(UPSTREAM_HEADERS)
        )

    return TestClient(app)


@pytest.mark.parametrize(
    ("path", "expected_status_code"),
    [
        ("/passthrough/block", 200),
        ("/passthrough/stream", 200),
        ("/error", 400),
    ],
    ids=["mounted-block", "mounted-stream", "dial-exception"],
)
def test_non_forwardable_headers_are_stripped(
    client: TestClient, path: str, expected_status_code: int
):
    response = client.get(path)

    assert response.status_code == expected_status_code
    assert "transfer-encoding" not in response.headers
    assert "connection" not in response.headers
    assert "server" not in response.headers
    assert "date" not in response.headers
    # The application headers are relayed untouched.
    assert response.headers["content-type"] == "application/json"
    assert response.headers["x-request-id"] == "req-1"


def test_content_length_of_the_emitted_body_is_kept(client: TestClient):
    response = client.get("/passthrough/block")

    assert response.headers["content-length"] == "8"


def test_strip_stale_content_headers():
    headers = httpx.Headers(
        {
            "Content-Length": "1234",
            "Content-Encoding": "gzip",
            "Content-Type": "application/json",
        }
    )

    strip_stale_content_headers(headers)

    assert dict(headers) == {"content-type": "application/json"}
