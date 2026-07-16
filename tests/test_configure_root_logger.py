import logging
import sys

import pytest

from aidial_sdk import configure_root_logger


def _stderr_console_handlers(root):
    return [
        h
        for h in root.handlers
        if isinstance(h, logging.StreamHandler)
        and getattr(h, "stream", None) is sys.stderr
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


def test_defers_to_existing_stderr_console_handler(clean_root):
    # Stand-in for OTEL's basicConfig console handler on root.
    otel_console = logging.StreamHandler(sys.stderr)
    clean_root.addHandler(otel_console)

    configure_root_logger()

    # We do not add our own; OTEL's stays as the only console handler.
    assert _stderr_console_handlers(clean_root) == [otel_console]
