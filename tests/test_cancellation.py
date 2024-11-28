import asyncio
from typing import Optional

import pytest

from aidial_sdk.chat_completion.response import (
    Response as ChatCompletionResponse,
)
from aidial_sdk.utils.streaming import add_heartbeat
from tests.utils.constants import DUMMY_DIAL_REQUEST


class Counter:
    done: int = 0
    cancelled: int = 0
    _lock: asyncio.Lock

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def inc_done(self):
        async with self._lock:
            self.done += 1

    async def inc_cancelled(self):
        async with self._lock:
            self.cancelled += 1


async def _wait_forever():
    await asyncio.Event().wait()


async def _wait(counter: Counter, secs: Optional[int] = None):
    try:
        if secs is None:
            await _wait_forever()
        else:
            for _ in range(secs):
                await asyncio.sleep(1)
    except asyncio.CancelledError:
        await counter.inc_cancelled()
        raise
    else:
        await counter.inc_done()


def chat_completion_wait_forever(counter: Counter):

    async def _chat_completion(*args, **kwargs):
        await _wait(counter)

    return _chat_completion


def chat_completion_gather(counter: Counter):

    async def _chat_completion(*args, **kwargs):
        tasks = (asyncio.create_task(_wait(counter)) for _ in range(10))
        await asyncio.gather(*tasks)

    return _chat_completion


def chat_completion_create_task(counter: Counter):

    async def _chat_completion(*args, **kwargs):
        for _ in range(10):
            asyncio.create_task(_wait(counter, 3))
        await _wait_forever()

    return _chat_completion


@pytest.mark.parametrize("with_heartbeat", [True, False])
@pytest.mark.parametrize(
    "chat_completion, expected_cancelled, expected_done",
    [
        (chat_completion_wait_forever, 1, 0),
        (chat_completion_gather, 10, 0),
        (chat_completion_create_task, 0, 10),
    ],
)
async def test_cancellation(
    with_heartbeat: bool, chat_completion, expected_cancelled, expected_done
):

    response = ChatCompletionResponse(DUMMY_DIAL_REQUEST)

    counter = Counter()
    chat_completion = chat_completion(counter)

    async def _exhaust_stream(stream):
        async for _ in stream:
            pass

    try:
        stream = response._generate_stream(chat_completion)
        if with_heartbeat:
            stream = add_heartbeat(
                stream,
                heartbeat_interval=0.2,
                heartbeat_object=": heartbeat\n\n",
            )

        await asyncio.wait_for(_exhaust_stream(stream), timeout=2)
    except asyncio.TimeoutError:
        pass
    else:
        assert False, "Stream should have timed out"

    await asyncio.sleep(2)

    assert (
        counter.cancelled == expected_cancelled
        and counter.done == expected_done
    ), "Stream should have been cancelled"
