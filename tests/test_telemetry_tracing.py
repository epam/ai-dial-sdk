from fastapi import FastAPI
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import SpanKind

from aidial_sdk.telemetry._context import (
    ResetContextMiddleware,
    reset_context_per_request,
)

CALLER_TRACE_ID = "b309d60a276d53212743377e6d1c19f8"
CALLER_SPAN_ID = "0fdf8f0e3f49fc04"
TRACEPARENT = f"00-{CALLER_TRACE_ID}-{CALLER_SPAN_ID}-01"


async def _ok(scope, receive, send) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b""})


async def _receive() -> dict:
    return {"type": "http.request", "body": b"", "more_body": False}


async def _post(app) -> None:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/messages",
        "raw_path": b"/v1/messages",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"traceparent", TRACEPARENT.encode())],
        "client": ("10.2.29.80", 54304),
        "server": ("10.2.28.67", 5000),
    }

    async def send(message) -> None:
        pass

    await app(scope, _receive, send)


async def test_traceparent_wins_over_a_context_left_by_another_request():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    app = ResetContextMiddleware(
        OpenTelemetryMiddleware(_ok, tracer_provider=provider)
    )

    # An ASGI server can start a request's task from inside the task serving
    # the previous request on the same connection, which copies its
    # contextvars - so the handler runs with a foreign span still current.
    with provider.get_tracer(__name__).start_as_current_span("previous"):
        await _post(app)

    servers = [
        span
        for span in exporter.get_finished_spans()
        if span.kind is SpanKind.SERVER
    ]
    assert len(servers) == 1
    assert f"{servers[0].context.trace_id:032x}" == CALLER_TRACE_ID
    assert f"{servers[0].parent.span_id:016x}" == CALLER_SPAN_ID


def test_reset_becomes_the_outermost_middleware():
    app = FastAPI()
    reset_context_per_request(app)
    assert isinstance(app.build_middleware_stack(), ResetContextMiddleware)
