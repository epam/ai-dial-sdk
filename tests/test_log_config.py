import json
import logging
import sys

import pytest
from uvicorn.logging import DefaultFormatter

from aidial_sdk.telemetry import init as telemetry_init
from aidial_sdk.utils import log_config
from aidial_sdk.utils._json_log_formatter import JsonLogFormatter
from aidial_sdk.utils.log_config import (
    _SDK_LOGGERS,
    LogConfig,
    configure_root_logger,
)


def test_arguments_override_env(monkeypatch):
    monkeypatch.setenv("DIAL_SDK_LOG", "warning")
    monkeypatch.setenv("DIAL_SDK_LOG_FORMAT", "text")

    config = LogConfig(level="debug", log_format="json")

    assert config.level == "DEBUG"  # normalized upper
    assert isinstance(config.formatter, JsonLogFormatter)


def test_falls_back_to_env_and_normalizes_case(monkeypatch):
    monkeypatch.setenv("DIAL_SDK_LOG", "error")
    monkeypatch.setenv("DIAL_SDK_LOG_FORMAT", "JSON")

    config = LogConfig()

    assert config.level == "ERROR"  # normalized upper
    assert isinstance(config.formatter, JsonLogFormatter)  # normalized lower


def test_text_format_builds_default_formatter():
    assert isinstance(LogConfig(log_format="text").formatter, DefaultFormatter)


def test_json_format_argument_wins_over_env(monkeypatch):
    monkeypatch.setenv("DIAL_SDK_JSON_LOG_FORMAT", '{"env": "%(message)s"}')

    config = LogConfig(log_format="json", json_format={"arg": "%(message)s"})
    record = logging.makeLogRecord({"msg": "hi"})

    assert json.loads(config.formatter.format(record)) == {"arg": "hi"}


@pytest.fixture
def clean_root():
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    root.handlers = []
    yield root
    root.handlers, root.level = saved_handlers, saved_level


@pytest.fixture
def clean_sdk_loggers():
    saved = {
        name: (logger.handlers[:], logger.propagate, logger.level)
        for name in _SDK_LOGGERS
        if (logger := logging.getLogger(name))
    }
    yield
    for name, (handlers, propagate, level) in saved.items():
        logger = logging.getLogger(name)
        logger.handlers, logger.propagate, logger.level = (
            handlers,
            propagate,
            level,
        )


def test_configure_root_logger_uses_passed_config(clean_root):
    configure_root_logger(LogConfig(log_format="json"))

    console = [
        h
        for h in clean_root.handlers
        if getattr(h, "stream", None) is sys.stderr
    ]
    assert len(console) == 1
    assert isinstance(console[0].formatter, JsonLogFormatter)


def test_console_export_defers_root_handler_to_otel(clean_root, monkeypatch):
    # The JSON console handler is installed by init_telemetry, so
    # configure_root_logger must not add its own stderr one.
    monkeypatch.setattr(telemetry_init, "otel_owns_console", True)

    configure_root_logger(LogConfig(level="info"))

    assert not any(
        getattr(h, "stream", None) is sys.stderr for h in clean_root.handlers
    )
    assert logging.getLogger("aidial_sdk").propagate is True


def test_routing_to_root_drops_the_competing_sdk_handlers(clean_sdk_loggers):
    # Whoever installed the root handler -- OTel or configure_root_logger() --
    # the SDK loggers must reach it instead of rendering on their own.
    log_config.configure_sdk_logger()

    log_config.route_sdk_loggers_to_root()

    for name in _SDK_LOGGERS:
        logger = logging.getLogger(name)
        assert logger.handlers == []
        assert logger.propagate is True
