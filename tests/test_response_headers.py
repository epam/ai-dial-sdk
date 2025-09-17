import pytest

from aidial_sdk.chat_completion import ChatCompletion, Request, Response
from tests.utils.client import create_app_client


class _BeforeGeneration(ChatCompletion):
    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        response.append_header("header1", "value1")
        response.append_header("header2", "value2-1")
        response.append_header("header2", "value2-2")

        with response.create_single_choice() as choice:
            await response.aflush()
            choice.append_content("hello world")


class _AfterGeneration(ChatCompletion):
    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        with response.create_single_choice() as choice:
            choice.append_content("hello world")
            await response.aflush()

            response.append_header("header1", "value1")
            response.append_header("header2", "value2-1")
            response.append_header("header2", "value2-2")


@pytest.mark.parametrize("stream", [False, True])
def test_append_response_header_before_generation(stream: bool):
    client = create_app_client(_BeforeGeneration())

    response = client.post(
        "chat/completions",
        json={
            "messages": [{"role": "user", "content": "test"}],
            "stream": stream,
        },
    )

    assert response.status_code == 200
    assert response.headers.get("missing-header") is None

    assert response.headers.get("header1") == "value1"
    assert response.headers.get("header2") == "value2-1, value2-2"


@pytest.mark.parametrize("stream", [False, True])
def test_append_response_header_after_generation(stream: bool, caplog):
    client = create_app_client(_AfterGeneration())

    response = client.post(
        "chat/completions",
        json={
            "messages": [{"role": "user", "content": "test"}],
            "stream": stream,
        },
    )

    assert response.headers.get("missing-header") is None
    assert "Trying to set a header after start of generation" in caplog.text

    if stream:
        assert response.status_code == 200
        assert (
            'data: {"error":{"message":"Error during processing the request","type":"runtime_error","code":"500"}}'
            in response.text
        )
    else:
        assert response.status_code == 500
        assert response.json() == {
            "error": {
                "message": "Error during processing the request",
                "type": "runtime_error",
                "code": "500",
            }
        }
