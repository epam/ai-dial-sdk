from unittest.mock import ANY

import anthropic
import pytest

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion import Request, Response
from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.exceptions import InvalidRequestError, ResourceNotFoundError
from tests.translators.messages_to_chat_completions.auto_translation.helpers import (
    AnthropicClient,
    AppClient,
    ScriptedChatCompletion,
    replying,
)

_RUNTIME_ERROR_MESSAGE = "Error during processing the request"


# (exception raised by the impl, status code, Anthropic error type, message)
_IMMEDIATE_ERRORS = pytest.mark.parametrize(
    "error, status_code, error_type, message",
    [
        (InvalidRequestError("bad"), 400, "invalid_request_error", "bad"),
        (
            DIALException("Slow down", status_code=429),
            429,
            "rate_limit_error",
            "Slow down",
        ),
        (
            ResourceNotFoundError("No such file"),
            404,
            "not_found_error",
            "No such file",
        ),
        (
            DIALException("Busy", status_code=503),
            503,
            "overloaded_error",
            "Busy",
        ),
        (RuntimeError("boom"), 500, "api_error", _RUNTIME_ERROR_MESSAGE),
    ],
    ids=[
        "invalid-request",
        "rate-limit",
        "not-found",
        "overloaded",
        "unexpected",
    ],
)

# (exception raised by the impl, Anthropic error type, message)
_MIDSTREAM_ERRORS = pytest.mark.parametrize(
    "error, error_type, message",
    [
        (InvalidRequestError("bad"), "invalid_request_error", "bad"),
        (
            DIALException("Slow down", status_code=429),
            "rate_limit_error",
            "Slow down",
        ),
        (
            ResourceNotFoundError("No such file"),
            "not_found_error",
            "No such file",
        ),
        (DIALException("Busy", status_code=503), "overloaded_error", "Busy"),
        (RuntimeError("boom"), "api_error", _RUNTIME_ERROR_MESSAGE),
    ],
    ids=[
        "invalid-request",
        "rate-limit",
        "not-found",
        "overloaded",
        "unexpected",
    ],
)


def _raising_client(
    error: Exception, *, after_first_chunk: bool
) -> AnthropicClient:
    async def _script(request: Request, response: Response) -> None:
        if after_first_chunk:
            with response.create_single_choice() as choice:
                choice.append_content("Hi")
                raise error
        else:
            raise error

    app = DIALApp().add_chat_completion(
        "foo",
        ScriptedChatCompletion(_script),
        expose_as_anthropic_messages=True,
    )
    return AppClient(app).anthropic()


def _error_body(error_type: str, message: object) -> dict[str, object]:
    return {"type": "error", "error": {"type": error_type, "message": message}}


@_IMMEDIATE_ERRORS
async def test_an_error_before_the_first_chunk_is_an_immediate_error(
    stream: bool,
    error: Exception,
    status_code: int,
    error_type: str,
    message: str,
) -> None:
    async with _raising_client(error, after_first_chunk=False) as client:
        with pytest.raises(anthropic.APIStatusError) as exc:
            await client.final_message(stream=stream)

    assert exc.value.status_code == status_code
    assert "application/json" in exc.value.response.headers["content-type"]
    assert exc.value.body == _error_body(error_type, message)


@_IMMEDIATE_ERRORS
async def test_an_error_after_the_first_chunk_of_a_block_response_is_an_immediate_error(
    error: Exception, status_code: int, error_type: str, message: str
) -> None:
    async with _raising_client(error, after_first_chunk=True) as client:
        with pytest.raises(anthropic.APIStatusError) as exc:
            await client.final_message(stream=False)

    assert exc.value.status_code == status_code
    assert exc.value.body == _error_body(error_type, message)


@_MIDSTREAM_ERRORS
async def test_an_error_after_the_first_chunk_ends_the_stream_with_an_error_event(
    error: Exception, error_type: str, message: str
) -> None:
    async with _raising_client(error, after_first_chunk=True) as client:
        with pytest.raises(anthropic.APIStatusError) as exc:
            await client.final_message(stream=True)

    assert exc.value.status_code == 200
    assert exc.value.body == _error_body(error_type, message)


async def test_the_events_before_a_midstream_error_are_delivered():
    events: list[str] = []

    async with _raising_client(
        InvalidRequestError("bad"), after_first_chunk=True
    ) as client:
        with pytest.raises(anthropic.APIStatusError):
            stream = await client.stream_events()
            async for event in stream:
                events.append(event.type)

    assert events == [
        "message_start",
        "content_block_start",
        "content_block_delta",
    ]


async def test_an_untranslatable_request_is_rejected_without_calling_the_impl(
    stream: bool,
) -> None:
    impl = replying("Hi")
    app = DIALApp().add_chat_completion(
        "foo", impl, expose_as_anthropic_messages=True
    )

    async with AppClient(app).anthropic() as client:
        with pytest.raises(anthropic.BadRequestError) as exc:
            await client.final_message(
                stream=stream,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {"type": "file", "file_id": "f1"},
                            }
                        ],
                    }
                ],
            )

    assert exc.value.body == _error_body("invalid_request_error", ANY)
    assert impl.requests == []


async def test_a_request_without_an_api_key_is_rejected(stream: bool) -> None:
    app = DIALApp().add_chat_completion(
        "foo", replying("Hi"), expose_as_anthropic_messages=True
    )

    async with AppClient(app).anthropic() as client:
        with pytest.raises(anthropic.BadRequestError) as exc:
            await client.final_message(
                stream=stream, extra_headers={"api-key": anthropic.omit}
            )

    assert exc.value.body == _error_body(
        "invalid_request_error", "Api-Key header is required"
    )
