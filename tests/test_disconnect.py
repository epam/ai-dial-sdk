import asyncio
import contextlib

import httpx
import pytest

from aidial_sdk.chat_completion import ChatCompletion


class WaitingApp(ChatCompletion):
    non_empty_stream: bool

    def __init__(self, non_empty_stream: bool):
        self.non_empty_stream = non_empty_stream

        self.is_cancelled = False
        self._started = None
        self._cancelled = None

    @property
    def started(self) -> asyncio.Event:
        # NOTE: lazily init events to ensure that they are
        # attached to the event loop inside the uvicorn thread,
        # instead of the test's event loop.
        if self._started is None:
            self._started = asyncio.Event()
        return self._started

    @property
    def cancelled(self) -> asyncio.Event:
        if self._cancelled is None:
            self._cancelled = asyncio.Event()
        return self._cancelled

    async def _wait(self):
        for _ in range(1000):
            await asyncio.sleep(1)

    async def chat_completion(self, request, response) -> None:
        try:
            self.started.set()

            if self.non_empty_stream:
                with response.create_single_choice():
                    await self._wait()
            else:
                await self._wait()

        except asyncio.CancelledError:
            self.is_cancelled = True
            self.cancelled.set()
            raise


@pytest.fixture(
    params=[False, True],
    ids=lambda b: "non-empty" if b else "empty",
)
def non_empty_stream(request) -> bool:
    return request.param


@pytest.fixture
def chat_completion(non_empty_stream):
    return WaitingApp(non_empty_stream)


@pytest.mark.slow
@pytest.mark.parametrize(
    "stream", [False, True], ids=lambda b: "stream" if b else "block"
)
async def test_disconnect(
    stream: bool,
    non_empty_stream: bool,
    chat_completion: WaitingApp,
    test_http_client: httpx.AsyncClient,
):
    await run_disconnect_test(stream, chat_completion, test_http_client)


async def run_disconnect_test(
    stream: bool,
    chat_completion: WaitingApp,
    test_http_client: httpx.AsyncClient,
):
    task = asyncio.create_task(
        test_http_client.post(
            "/chat/completions",
            json={
                "messages": [{"role": "user", "content": "hello"}],
                "stream": stream,
            },
            timeout=2,
        )
    )

    await asyncio.wait_for(chat_completion.started.wait(), timeout=1)
    await test_http_client.aclose()

    await asyncio.wait_for(chat_completion.cancelled.wait(), timeout=1)
    assert chat_completion.is_cancelled

    with contextlib.suppress(httpx.ReadError):
        await task
