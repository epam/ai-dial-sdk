import asyncio

import anthropic
import pytest
from anthropic.types import TextBlock

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion import Request, Response
from aidial_sdk.exceptions import InvalidRequestError
from tests.translators.messages_to_chat_completions.auto_translation.helpers import (
    AnthropicClient,
    AppClient,
    Chat,
    ScriptedChatCompletion,
)

_EVENTS_WITHOUT_PINGS = [
    "message_start",
    "content_block_start",
    "content_block_delta",
    "content_block_delta",
    "content_block_stop",
    "message_delta",
    "message_stop",
]


async def _idle_before_each_chunk(request: Request, response: Response) -> None:
    await asyncio.sleep(2)
    with response.create_single_choice() as choice:
        choice.append_content("Hi")
        await asyncio.sleep(2)
        choice.append_content(" there")


async def _idle_then_fail(request: Request, response: Response) -> None:
    await asyncio.sleep(2)
    raise InvalidRequestError("bad")


def _anthropic_client(
    chat: Chat, heartbeat_interval: float | None
) -> AnthropicClient:
    app = DIALApp().add_chat_completion(
        "foo",
        ScriptedChatCompletion(chat),
        heartbeat_interval=heartbeat_interval,
        expose_as_anthropic_messages=True,
    )
    return AppClient(app).anthropic()


@pytest.mark.virtual_clock
async def test_pings_are_sent_while_the_impl_is_idle():
    async with _anthropic_client(
        _idle_before_each_chunk, heartbeat_interval=1.5
    ) as client:
        events = await client.stream_event_names()

    assert events == [
        "ping",
        "message_start",
        "content_block_start",
        "content_block_delta",
        "ping",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]


@pytest.mark.virtual_clock
async def test_no_pings_are_sent_without_a_heartbeat_interval():
    async with _anthropic_client(
        _idle_before_each_chunk, heartbeat_interval=None
    ) as client:
        events = await client.stream_event_names()

    assert events == _EVENTS_WITHOUT_PINGS


@pytest.mark.virtual_clock
@pytest.mark.parametrize(
    "heartbeat_interval, status_code",
    [(3.0, 400), (1.5, 200)],
    ids=["before-the-first-ping", "after-the-first-ping"],
)
async def test_an_error_is_an_http_error_only_before_the_first_ping(
    heartbeat_interval: float, status_code: int
):
    async with _anthropic_client(
        _idle_then_fail, heartbeat_interval=heartbeat_interval
    ) as client:
        with pytest.raises(anthropic.APIStatusError) as exc:
            await client.final_message(stream=True)

    assert exc.value.status_code == status_code
    assert exc.value.body == {
        "type": "error",
        "error": {"type": "invalid_request_error", "message": "bad"},
    }


@pytest.mark.virtual_clock
async def test_heartbeats_do_not_alter_the_message(stream: bool):
    async with _anthropic_client(
        _idle_before_each_chunk, heartbeat_interval=1.5
    ) as client:
        message = await client.final_message(stream=stream)

    assert message.content == [TextBlock(type="text", text="Hi there")]
