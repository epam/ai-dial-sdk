import json
import logging
import os
import subprocess
import sys

import pytest

from aidial_sdk.telemetry.init import init_telemetry
from aidial_sdk.telemetry.types import LogsConfig, TelemetryConfig


@pytest.fixture
def clean_root():
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    root.handlers = []
    yield root
    root.handlers, root.level = saved_handlers, saved_level


def test_console_export_replaces_stderr_handler_with_otel(clean_root):
    from opentelemetry.sdk._logs import LoggingHandler

    config = TelemetryConfig(
        logs=LogsConfig(otlp_export=False, console_export=True),
        tracing=None,
        metrics=None,
    )
    # A leftover text stderr handler must be dropped in favor of the OTel one.
    clean_root.addHandler(logging.StreamHandler(sys.stderr))

    init_telemetry(app=None, config=config)

    assert not any(
        isinstance(h, logging.StreamHandler) and h.stream is sys.stderr
        for h in clean_root.handlers
    )
    assert any(isinstance(h, LoggingHandler) for h in clean_root.handlers)


# init_telemetry sets a process-global logger provider (set-once), so the
# exporter must be exercised in a fresh subprocess to see its real stderr.
def test_console_export_emits_single_line_json():
    script = (
        "import logging\n"
        "from aidial_sdk.telemetry.init import init_telemetry\n"
        "from aidial_sdk.telemetry.types import LogsConfig, TelemetryConfig\n"
        "init_telemetry(None, TelemetryConfig("
        "logs=LogsConfig(otlp_export=False, console_export=True),"
        "tracing=None, metrics=None))\n"
        "log = logging.getLogger('app')\n"
        "log.setLevel(logging.INFO)\n"
        "log.info('hello')\n"
    )
    err = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script], capture_output=True, text=True
    ).stderr

    lines = [ln for ln in err.splitlines() if ln.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["body"] == "hello"


# A per-logger DEBUG level set by the app must reach the console exporter — the
# OTel handler must not impose its own level floor over the app's choice.
def test_console_export_honors_per_logger_debug_level():
    script = (
        "import logging\n"
        "from aidial_sdk.telemetry.init import init_telemetry\n"
        "from aidial_sdk.telemetry.types import LogsConfig, TelemetryConfig\n"
        "init_telemetry(None, TelemetryConfig("
        "logs=LogsConfig(otlp_export=False, console_export=True),"
        "tracing=None, metrics=None))\n"
        "log = logging.getLogger('app')\n"
        "log.setLevel(logging.DEBUG)\n"
        "log.debug('hello-debug')\n"
    )
    err = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script], capture_output=True, text=True
    ).stderr

    lines = [ln for ln in err.splitlines() if ln.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["body"] == "hello-debug"


# Run in a subprocess so `import openai` installs its own root stderr handler at
# import time (OPENAI_LOG=debug) — exactly as in a real app — and so the tracing
# instrumentors don't leak into the test process's global state.
def test_otel_correlation_takes_over_third_party_handler():
    script = (
        "import logging\n"
        "import openai  # OPENAI_LOG=debug: grabs root stderr handler on import\n"
        "from aidial_sdk.telemetry.init import init_telemetry\n"
        "from aidial_sdk.telemetry.types import TelemetryConfig, TracingConfig\n"
        "init_telemetry(None, TelemetryConfig("
        "tracing=TracingConfig(logging=True), logs=None, metrics=None))\n"
        "logging.getLogger('app').warning('hello')\n"
    )
    err = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        # No OTEL_PYTHON_LOG_CORRELATION here: TracingConfig(logging=True) alone
        # must drive set_logging_format, proving the config field is wired.
        env={
            **os.environ,
            "OPENAI_LOG": "debug",
            "OTEL_PYTHON_LOG_FORMAT": "OTELFMT %(levelname)s trace=%(otelTraceID)s %(message)s",
        },
    ).stderr

    # OTel's correlation format wins; OpenAI's "[... - app:NN - ...]" format is gone.
    assert "OTELFMT WARNING trace=0 hello" in err
    assert "- app:" not in err
