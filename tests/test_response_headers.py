import pytest

from aidial_sdk.chat_completion import ChatCompletion, Request, Response
from tests.utils.client import create_app_client


class _App(ChatCompletion):
    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        response.set_header("header1", "value1")

        with response.create_single_choice() as choice:
            choice.append_content("hello")
            choice.append_content(" world")
            await response.aflush()

            response.set_header("header2", "value2")


@pytest.mark.parametrize("stream", [False, True])
def test_response_header(stream: bool):
    client = create_app_client(_App())

    response = client.post(
        "chat/completions",
        json={
            "messages": [{"role": "user", "content": "test"}],
            "stream": stream,
        },
    )

    assert response.headers.get("missing-header") is None

    assert response.headers.get("header1") == "value1"
    assert response.headers.get("header2") == (None if stream else "value2")
