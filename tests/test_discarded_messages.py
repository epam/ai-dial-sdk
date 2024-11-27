import pytest

from aidial_sdk import HTTPException
from aidial_sdk.chat_completion import ChatCompletion, Request, Response
from tests.utils.chunks import check_sse_stream, create_single_choice_chunk
from tests.utils.client import create_app_client
from tests.utils.constants import DUMMY_DIAL_REQUEST

DISCARDED_MESSAGES = list(range(0, 12))


def test_discarded_messages_returned():
    class _Impl(ChatCompletion):
        async def chat_completion(
            self, request: Request, response: Response
        ) -> None:
            with response.create_single_choice():
                pass
            response.set_discarded_messages(DISCARDED_MESSAGES)

    client = create_app_client(_Impl())

    response = client.post(
        "chat/completions",
        json={"messages": [{"role": "user", "content": "Test"}]},
    )

    assert (
        response.json()["statistics"]["discarded_messages"]
        == DISCARDED_MESSAGES
    )


def test_discarded_messages_returned_as_last_chunk_in_stream():
    class _Impl(ChatCompletion):
        async def chat_completion(
            self, request: Request, response: Response
        ) -> None:
            response.set_response_id("test_id")
            response.set_created(0)

            with response.create_single_choice():
                pass

            response.set_discarded_messages(DISCARDED_MESSAGES)

    client = create_app_client(_Impl())

    response = client.post(
        "chat/completions",
        json={
            "messages": [{"role": "user", "content": "Test content"}],
            "stream": True,
        },
    )

    check_sse_stream(
        response.iter_lines(),
        [
            create_single_choice_chunk({"role": "assistant"}),
            create_single_choice_chunk(
                {},
                finish_reason="stop",
                statistics={"discarded_messages": DISCARDED_MESSAGES},
            ),
        ],
    )


def test_discarded_messages_is_set_twice():
    response = Response(DUMMY_DIAL_REQUEST)

    with response.create_single_choice():
        pass

    response.set_discarded_messages(DISCARDED_MESSAGES)

    with pytest.raises(HTTPException):
        response.set_discarded_messages(DISCARDED_MESSAGES)


def test_discarded_messages_is_set_before_choice():
    response = Response(DUMMY_DIAL_REQUEST)

    with pytest.raises(HTTPException):
        response.set_discarded_messages(DISCARDED_MESSAGES)
