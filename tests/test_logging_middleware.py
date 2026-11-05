import logging

import pytest

from tests.applications.single_choice import SingleChoiceApplication
from tests.utils.client import create_app_client


def test_debug_logging_emits_each_stream_chunk_once(
    caplog: pytest.LogCaptureFixture,
):
    client = create_app_client(SingleChoiceApplication())

    with caplog.at_level(logging.DEBUG, logger="aidial_sdk"):
        response = client.post(
            "chat/completions",
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        )

    assert response.status_code == 200
    messages = [
        r.getMessage() for r in caplog.records if r.name == "aidial_sdk"
    ]
    events = [m.split("data: ", 1)[1] for m in messages if "data: " in m]
    assert events and len(events) == len(set(events))
