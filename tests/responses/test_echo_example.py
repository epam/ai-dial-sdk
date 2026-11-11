"""examples/echo_responses answers the curl in its README."""

import pytest

from examples.echo_responses.app import app
from tests.responses.conftest import check_http
from tests.utils.client import create_test_client


@pytest.mark.parametrize("stream", [False, True])
def test_echo(stream: bool):
    client = create_test_client(app, name="echo")

    http = client.post(
        "responses", json={"input": "Repeat me!", "stream": stream}
    )

    transcript = check_http(http)
    assert http.status_code == 200
    assert transcript.body is not None
    assert transcript.body["status"] == "completed"
    assert transcript.body["model"] == "echo"
    [item] = transcript.body["output"]
    assert item["type"] == "message"
    assert item["content"] == [
        {
            "type": "output_text",
            "text": "Repeat me!",
            "annotations": [],
            "logprobs": [],
        }
    ]
