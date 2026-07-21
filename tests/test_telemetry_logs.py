import json
import logging
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
