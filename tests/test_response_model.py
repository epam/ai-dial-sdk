import pytest

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion import ChatCompletion, Request, Response
from tests.utils.chunks import check_sse_stream, create_single_choice_chunk
from tests.utils.client import create_test_client

_UPSTREAM_DEPLOYMENT = "upstream-deployment"
_USER_DEPLOYMENT = "user-deployment"

_RUNTIME_ERROR = {
    "error": {
        "message": "Error during processing the request",
        "type": "runtime_error",
        "code": "500",
    }
}


class _ModelSetter(ChatCompletion):
    def __init__(self, model: str | None, *, after_start: bool = False):
        self.model = model
        self.after_start = after_start

    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        response.set_response_id("test_id")
        response.set_created(0)

        if self.model is not None and not self.after_start:
            response.set_model(self.model)

        with response.create_single_choice() as choice:
            if self.model is not None and self.after_start:
                response.set_model(self.model)
            choice.append_content("Hi")


def _post(impl: ChatCompletion, *, stream: bool):
    app = DIALApp().add_chat_completion(_UPSTREAM_DEPLOYMENT, impl)
    client = create_test_client(
        app,
        name=_UPSTREAM_DEPLOYMENT,
        headers={
            "api-key": "TEST_API_KEY",
            "x-dial-deployment-id": _USER_DEPLOYMENT,
        },
    )
    return client.post(
        "chat/completions",
        json={
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": stream,
        },
    )


_MODELS = pytest.mark.parametrize(
    "model, expected_model",
    [(None, _USER_DEPLOYMENT), ("gpt-5.5", "gpt-5.5")],
    ids=["model-not-set", "model-set"],
)


@_MODELS
def test_the_model_of_a_block_response(model: str | None, expected_model: str):
    response = _post(_ModelSetter(model), stream=False)

    assert response.status_code == 200
    assert response.json()["model"] == expected_model


@_MODELS
def test_the_model_of_a_streaming_response(
    model: str | None, expected_model: str
):
    response = _post(_ModelSetter(model), stream=True)

    check_sse_stream(
        response.iter_lines(),
        [
            create_single_choice_chunk(
                delta={"role": "assistant"}, model=expected_model
            ),
            create_single_choice_chunk(
                delta={"content": "Hi"}, model=expected_model
            ),
            create_single_choice_chunk(
                finish_reason="stop", model=expected_model
            ),
        ],
    )


def test_setting_the_model_after_the_start_fails_a_block_response(
    caplog: pytest.LogCaptureFixture,
):
    response = _post(_ModelSetter("gpt-5.5", after_start=True), stream=False)

    assert response.status_code == 500
    assert response.json() == _RUNTIME_ERROR
    assert 'Trying to set "model" after start of generation' in caplog.text


def test_setting_the_model_after_the_start_fails_a_streaming_response(
    caplog: pytest.LogCaptureFixture,
):
    response = _post(_ModelSetter("gpt-5.5", after_start=True), stream=True)

    check_sse_stream(
        response.iter_lines(),
        [
            create_single_choice_chunk(
                delta={"role": "assistant"}, model=_USER_DEPLOYMENT
            ),
            _RUNTIME_ERROR,
        ],
    )
    assert 'Trying to set "model" after start of generation' in caplog.text
