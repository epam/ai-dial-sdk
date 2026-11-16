"""examples/echo_responses answers the curl in its README."""

from pathlib import Path

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


@pytest.mark.parametrize(
    "input",
    [
        [],
        [
            {"type": "function_call_output", "call_id": "c1", "output": "1"},
            {"type": "function_call_output", "call_id": "c2", "output": "2"},
        ],
    ],
    ids=["empty", "tool_results_only"],
)
@pytest.mark.parametrize("stream", [False, True])
def test_echo_without_messages(input: list, stream: bool):
    client = create_test_client(app, name="echo")

    http = client.post("responses", json={"input": input, "stream": stream})

    transcript = check_http(http)
    assert http.status_code == 200, http.text
    assert transcript.body is not None
    assert transcript.body["status"] == "completed"


def test_readme_snippet_is_the_example():
    # The README reproduces the example as the canonical handler
    root = Path(__file__).parents[2]
    readme = (root / "README.md").read_text()
    section = readme.split("#### Echo Responses example\n", 1)[1]
    snippet = section.split("```python\n", 1)[1].split("```\n", 1)[0]

    assert snippet == (root / "examples/echo_responses/app.py").read_text()
