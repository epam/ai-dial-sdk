import logging

import pytest

from aidial_sdk import configure_root_logger
from aidial_sdk.utils.log_config import _CONSOLE_HANDLER_MARKER


def _console_handlers(root):
    return [
        h for h in root.handlers if getattr(h, _CONSOLE_HANDLER_MARKER, False)
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
    assert len(_console_handlers(clean_root)) == 1


def test_idempotent_and_preserves_other_handlers(clean_root):
    other = logging.NullHandler()  # stands in for the OTLP export handler
    clean_root.addHandler(other)

    configure_root_logger()
    configure_root_logger()  # repeat must not stack console handlers

    assert len(_console_handlers(clean_root)) == 1
    assert other in clean_root.handlers


def test_level_none_leaves_root_level_untouched(clean_root):
    clean_root.setLevel(logging.WARNING)
    configure_root_logger()
    assert clean_root.level == logging.WARNING
    configure_root_logger(level="DEBUG")
    assert clean_root.level == logging.DEBUG
