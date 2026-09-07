import logging
import sys

import pytest
from opentelemetry.instrumentation.logging import LoggingInstrumentor

from aidial_sdk import configure_root_logger
from aidial_sdk.utils import log_config


def _stderr_console_handlers(root):
    return [
        h
        for h in root.handlers
        if isinstance(h, logging.StreamHandler) and h.stream is sys.stderr
    ]


@pytest.fixture
def clean_root():
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    root.handlers = []
    yield root
    root.handlers, root.level = saved_handlers, saved_level


def test_installs_single_console_handler(clean_root):
    configure_root_logger()
    assert len(_stderr_console_handlers(clean_root)) == 1


def test_idempotent_and_preserves_other_handlers(clean_root):
    other = logging.NullHandler()  # stands in for the OTLP export handler
    clean_root.addHandler(other)

    configure_root_logger()
    configure_root_logger()  # repeat must not stack console handlers

    assert len(_stderr_console_handlers(clean_root)) == 1
    assert other in clean_root.handlers


def test_takes_over_foreign_stderr_console_handler(clean_root):
    # Stand-in for the basicConfig handler ANTHROPIC_LOG/OPENAI_LOG install.
    foreign = logging.StreamHandler(sys.stderr)
    clean_root.addHandler(foreign)

    configure_root_logger()

    # Foreign handler dropped; ours is the only console handler.
    assert len(_stderr_console_handlers(clean_root)) == 1
    assert foreign not in clean_root.handlers


def test_defers_to_otel_correlation_handler(clean_root, monkeypatch):
    monkeypatch.setattr(log_config, "_otel_owns_console", True)
    otel_console = logging.StreamHandler(sys.stderr)
    clean_root.addHandler(otel_console)

    configure_root_logger()

    # OTEL owns the console format; we defer and leave its handler alone.
    assert _stderr_console_handlers(clean_root) == [otel_console]


def test_keeps_sdk_handler_until_otel_claims_the_console(clean_root):
    # init_telemetry() reports the takeover, and it may never run — telemetry is
    # opt-in. Deferring to a handler nobody installed would drop every record
    # into logging's unformatted lastResort.
    assert log_config._otel_owns_console is False

    configure_root_logger()

    assert len(_stderr_console_handlers(clean_root)) == 1


def test_honors_otel_python_log_format(clean_root, monkeypatch, capsys):
    monkeypatch.setattr(log_config, "_otel_owns_console", True)
    monkeypatch.setenv("OTEL_PYTHON_LOG_CORRELATION", "true")
    monkeypatch.setenv(
        "OTEL_PYTHON_LOG_FORMAT",
        "trace=%(otelTraceID)s | %(levelname)s | %(message)s",
    )

    # OTel installs the root console handler (basicConfig) in its format;
    # basicConfig only does so when root has no handlers, so drop pytest's.
    clean_root.handlers = []
    LoggingInstrumentor().instrument()
    try:
        configure_root_logger()  # defers, leaving OTel's handler in place

        logging.getLogger("some.app.logger").warning("hello")
    finally:
        LoggingInstrumentor().uninstrument()

    # No active span, so otelTraceID is "0"; line matches OTEL_PYTHON_LOG_FORMAT.
    assert capsys.readouterr().err.strip() == "trace=0 | WARNING | hello"
