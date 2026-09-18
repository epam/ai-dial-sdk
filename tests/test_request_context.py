import asyncio
import socket
import threading
from collections.abc import MutableMapping
from contextlib import nullcontext
from typing import Any

import uvicorn
from fastapi import Request
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import SpanKind

from aidial_sdk import DIALApp
from aidial_sdk.telemetry._context import reset_trace_context
from aidial_sdk.telemetry.types import TelemetryConfig, TracingConfig
from aidial_sdk.utils.logging import deployment_id, set_log_deployment

CALLERS = [
    ("b309d60a276d53212743377e6d1c19f8", "0fdf8f0e3f49fc04"),
    ("07907a4cbb3d47f1b6ba1e1b0f1a2c3d", "4d43e1bb82801370"),
]

# Past uvicorn's HIGH_WATER_LIMIT, which is what makes a request pause reading
# and then resume it from its own task - the step that pins that task's
# context to the connection. See `reset_trace_context`.
BODY = b"x" * 200_000


def _read_response(reader: Any) -> None:
    length = 0
    while True:
        line = reader.readline()
        if line in (b"\r\n", b"\n", b""):
            break
        name, _, value = line.decode().partition(":")
        if name.lower() == "content-length":
            length = int(value.strip())
    if length:
        reader.read(length)


def _post_all_on_one_connection(port: int) -> None:
    """Sends one request per caller over a single keep-alive connection.

    Strictly sequential: each response is read in full before the next request
    is written, so nothing here relies on pipelining.
    """
    conn = socket.create_connection(("127.0.0.1", port), timeout=10)
    try:
        reader = conn.makefile("rb")
        for trace_id, span_id in CALLERS:
            conn.sendall(
                b"POST /echo HTTP/1.1\r\n"
                b"Host: 127.0.0.1\r\n"
                b"Content-Type: application/json\r\n"
                b"traceparent: "
                + f"00-{trace_id}-{span_id}-01".encode()
                + b"\r\n"
                b"Content-Length: " + str(len(BODY)).encode() + b"\r\n"
                b"\r\n" + BODY
            )
            _read_response(reader)
        reader.close()
    finally:
        conn.close()


async def test_each_request_is_traced_under_its_own_traceparent():
    """A request must never be filed under an earlier request's trace.

    Drives a real `DIALApp` through a real uvicorn over one keep-alive
    connection. This exercises the wiring as well as the logic: the reset only
    works if it happens outside `FastAPIInstrumentor`'s own middleware, which
    is why it lives in `DIALApp.__call__`.
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    app = DIALApp()

    @app.post("/echo")
    async def _echo(request: Request) -> dict[str, int]:
        return {"len": len(await request.body())}

    # What `configure_telemetry` does, minus the global tracer provider that a
    # test must not install.
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    app._reset_otel_context = reset_trace_context

    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(8)
    port = sock.getsockname()[1]

    server = uvicorn.Server(
        uvicorn.Config(app, log_level="warning", access_log=False)
    )
    thread = threading.Thread(
        target=lambda: asyncio.run(server.serve(sockets=[sock])), daemon=True
    )
    thread.start()
    try:
        while not server.started:
            await asyncio.sleep(0.05)
        await asyncio.get_running_loop().run_in_executor(
            None, _post_all_on_one_connection, port
        )
    finally:
        server.should_exit = True
        thread.join(timeout=10)

    servers = {
        f"{span.context.trace_id:032x}": span.parent
        for span in exporter.get_finished_spans()
        if span.kind is SpanKind.SERVER and span.context is not None
    }

    assert sorted(servers) == sorted(trace_id for trace_id, _ in CALLERS)
    for trace_id, span_id in CALLERS:
        parent = servers[trace_id]
        assert parent is not None
        assert f"{parent.span_id:016x}" == span_id


def test_telemetry_installs_the_trace_context_reset(monkeypatch):
    monkeypatch.setattr(
        "aidial_sdk.telemetry.init.init_telemetry", lambda app, config: None
    )

    assert DIALApp()._reset_otel_context is nullcontext

    app = DIALApp(
        telemetry_config=TelemetryConfig(
            tracing=TracingConfig(otlp_export=False)
        )
    )
    assert app._reset_otel_context is reset_trace_context


async def test_deployment_id_is_not_inherited_from_another_request():
    """The log prefix must not name an earlier request's deployment.

    `set_log_deployment` is called inside the route handler, so anything
    logged before that - a client disconnect, a validation error - reads
    whatever the contextvar held on entry. That must not be another request's
    deployment.
    """
    app = DIALApp()
    seen: list[str | None] = []

    @app.get("/probe")
    async def _probe() -> dict[str, str]:
        seen.append(deployment_id.get())
        return {}

    set_log_deployment("leaked-from-an-earlier-request")

    # One body message, then park. `DisconnectMiddleware`'s poller loops on
    # `receive()` until it sees `http.disconnect`, and a stub that returns
    # immediately every time would spin without ever yielding to the handler.
    delivered = asyncio.Event()

    async def receive() -> dict[str, Any]:
        if not delivered.is_set():
            delivered.set()
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def send(message: MutableMapping[str, Any]) -> None:
        pass

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/probe",
            "raw_path": b"/probe",
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "client": ("10.2.29.80", 54304),
            "server": ("10.2.28.67", 5000),
        },
        receive,
        send,
    )

    assert seen == [None]
