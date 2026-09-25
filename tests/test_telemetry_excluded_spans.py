"""OTEL_PYTHON_FASTAPI_EXCLUDE_SPANS.

The setting is read into module-level constants at import time, so each case
runs in its own interpreter with its own environment, the same way
`test_telemetry_logs.py` does it.
"""

import json
import os
import subprocess
import sys

import pytest

# Instruments a FastAPI app that streams three chunks, drives one request
# through it with an in-memory exporter attached, and prints the names of the
# spans that came out. That exercises the real instrumentation rather than
# just the config plumbing.
_SCRIPT = """
import json

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import set_tracer_provider

from aidial_sdk.telemetry.init import init_telemetry
from aidial_sdk.telemetry.types import TelemetryConfig, TracingConfig

exporter = InMemorySpanExporter()
provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(exporter))
set_tracer_provider(provider)

app = FastAPI()


@app.post("/stream")
async def stream():
    async def body():
        for _ in range(3):
            yield b"chunk"

    return StreamingResponse(body(), media_type="text/event-stream")


config = TelemetryConfig(tracing=TracingConfig(otlp_export=False))
print("CONFIG " + json.dumps(config.tracing.excluded_asgi_spans))

init_telemetry(app, config)

with TestClient(app) as client:
    assert client.post("/stream").status_code == 200

names = sorted({span.name for span in exporter.get_finished_spans()})
print("SPANS " + json.dumps(names))
"""


def run(env: dict[str, str] | None = None) -> tuple[list[str], list[str]]:
    """Return (configured exclusions, span names emitted)."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", _SCRIPT],
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )
    assert result.returncode == 0, result.stderr
    config: list[str] = []
    spans: list[str] = []
    for line in result.stdout.splitlines():
        if line.startswith("CONFIG "):
            config = json.loads(line[len("CONFIG ") :])
        elif line.startswith("SPANS "):
            spans = json.loads(line[len("SPANS ") :])
    return config, spans


def has_send(spans: list[str]) -> bool:
    return any(name.endswith("http send") for name in spans)


def has_receive(spans: list[str]) -> bool:
    return any(name.endswith("http receive") for name in spans)


def test_unset_keeps_current_behaviour():
    """The default must not change: both sub-spans are still emitted."""
    config, spans = run()
    assert config == []
    assert has_send(spans), spans
    assert has_receive(spans), spans


def test_excluding_both_drops_both():
    config, spans = run({"OTEL_PYTHON_FASTAPI_EXCLUDE_SPANS": "receive,send"})
    assert config == ["receive", "send"]
    assert not has_send(spans), spans
    assert not has_receive(spans), spans
    # The request span itself must survive -- that is the whole point.
    assert any("/stream" in name for name in spans), spans


def test_excluding_send_only():
    """A streaming deployment's one span per chunk is the `send` one."""
    config, spans = run({"OTEL_PYTHON_FASTAPI_EXCLUDE_SPANS": "send"})
    assert config == ["send"]
    assert not has_send(spans), spans
    assert has_receive(spans), spans


def test_excluding_receive_only():
    config, spans = run({"OTEL_PYTHON_FASTAPI_EXCLUDE_SPANS": "receive"})
    assert config == ["receive"]
    assert has_send(spans), spans
    assert not has_receive(spans), spans


@pytest.mark.parametrize("value", [" send , RECEIVE ", "Send,Receive", "SEND"])
def test_values_are_case_and_whitespace_insensitive(value: str):
    config, _ = run({"OTEL_PYTHON_FASTAPI_EXCLUDE_SPANS": value})
    assert config, f"{value!r} should have parsed to something"
    assert all(span in ("receive", "send") for span in config)


def test_unknown_values_are_ignored_not_fatal():
    """A typo must not take the app down, or silently exclude everything."""
    config, spans = run({"OTEL_PYTHON_FASTAPI_EXCLUDE_SPANS": "bogus,send,"})
    assert config == ["send"]
    assert not has_send(spans), spans
    assert has_receive(spans), spans


def test_empty_value_is_treated_as_unset():
    config, spans = run({"OTEL_PYTHON_FASTAPI_EXCLUDE_SPANS": ""})
    assert config == []
    assert has_send(spans), spans


def test_falls_back_when_instrumentation_is_too_old(monkeypatch, caplog):
    """An instrumentation without `exclude_spans` must not break start-up.

    The floor this package allows for opentelemetry-instrumentation-fastapi
    predates the parameter, so an operator who sets the variable against an
    old install should get a warning and an un-excluded app, not a crash.
    """
    import logging

    from fastapi import FastAPI

    from aidial_sdk.telemetry import init as telemetry_init
    from aidial_sdk.telemetry.types import TelemetryConfig, TracingConfig

    calls: list[dict] = []

    class _OldInstrumentor:
        @staticmethod
        def instrument_app(app, **kwargs):
            calls.append(kwargs)
            if "exclude_spans" in kwargs:
                raise TypeError(
                    "instrument_app() got an unexpected keyword argument "
                    "'exclude_spans'"
                )

    monkeypatch.setattr(telemetry_init, "FastAPIInstrumentor", _OldInstrumentor)

    config = TelemetryConfig(
        tracing=TracingConfig(otlp_export=False, excluded_asgi_spans=["send"])
    )
    with caplog.at_level(logging.WARNING):
        telemetry_init._instrument_fastapi_app(FastAPI(), config)

    # Tried with the parameter, then retried without it.
    assert calls == [{"exclude_spans": ["send"]}, {}]
    assert "exclude_spans" in caplog.text
