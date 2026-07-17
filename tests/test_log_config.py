import json
import logging
import sys

import pytest
from uvicorn.logging import DefaultFormatter

from aidial_sdk.utils._json_log_formatter import JsonLogFormatter
from aidial_sdk.utils.log_config import LogConfig, configure_root_logger


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


def test_configure_root_logger_uses_passed_config(clean_root):
    configure_root_logger(LogConfig(log_format="json"))

    console = [
        h
        for h in clean_root.handlers
        if getattr(h, "stream", None) is sys.stderr
    ]
    assert len(console) == 1
    assert isinstance(console[0].formatter, JsonLogFormatter)
