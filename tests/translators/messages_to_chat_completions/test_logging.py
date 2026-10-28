import logging

import pytest

from tests.translators.messages_to_chat_completions.helpers import convert, user


def test_conversion_warnings_use_the_project_logger(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG, logger="aidial_sdk"):
        convert({**user("hi"), "top_k": 2, "inference_geo": "eu"})
    records = [
        record for record in caplog.records if record.name == "aidial_sdk"
    ]
    assert any(
        record.levelno == logging.WARNING
        and "top_k, inference_geo" in record.message
        for record in records
    )
