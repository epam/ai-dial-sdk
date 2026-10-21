import logging

import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import set_tracer_provider

from aidial_sdk.telemetry import init as telemetry_init

_exporter = InMemorySpanExporter()
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(_exporter))
set_tracer_provider(_provider)


def stream_one_request(exclude_spans: list[str]) -> list[str]:
    """Names of the spans a single streamed response produces."""
    app = FastAPI()

    @app.post("/stream")
    async def stream():
        return StreamingResponse(
            (b"chunk" for _ in range(3)), media_type="text/event-stream"
        )

    telemetry_init._instrument_fastapi_app(app, exclude_spans)

    _exporter.clear()
    with TestClient(app) as client:
        assert client.post("/stream").status_code == 200
    return [span.name for span in _exporter.get_finished_spans()]


@pytest.mark.parametrize(
    ("exclude_spans", "receive", "send"),
    [
        ([], True, True),
        (["send"], True, False),
        (["receive"], False, True),
        (["receive", "send"], False, False),
        (["bogus"], True, True),
    ],
)
def test_excluded_spans(exclude_spans: list[str], receive: bool, send: bool):
    names = stream_one_request(exclude_spans)
    assert any(n.endswith("http receive") for n in names) == receive, names
    assert any(n.endswith("http send") for n in names) == send, names
    # The request span itself always survives -- that is the whole point.
    assert any("/stream" in n for n in names), names


def test_falls_back_when_instrumentation_is_too_old(monkeypatch, caplog):
    """An instrumentation without `exclude_spans` must not break start-up."""
    calls: list[dict] = []

    class _OldInstrumentor:
        @staticmethod
        def instrument_app(app, **kwargs):
            calls.append(kwargs)
            if "exclude_spans" in kwargs:
                raise TypeError("unexpected keyword argument 'exclude_spans'")

    monkeypatch.setattr(telemetry_init, "FastAPIInstrumentor", _OldInstrumentor)

    with caplog.at_level(logging.WARNING):
        telemetry_init._instrument_fastapi_app(FastAPI(), ["send"])

    # Tried with the parameter, then retried without it.
    assert calls == [{"exclude_spans": ["send"]}, {}]
    assert "OTEL_PYTHON_FASTAPI_EXCLUDE_SPANS is ignored" in caplog.text
