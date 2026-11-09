import asyncio
import contextlib
import threading

import httpx
import pytest

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion import ChatCompletion
from tests.utils.leaving_client import serve_to_a_leaving_client


class WaitingApp(ChatCompletion):
    non_empty_stream: bool

    def __init__(self, non_empty_stream: bool):
        self.non_empty_stream = non_empty_stream

        self.is_cancelled = False

        self.started = threading.Event()
        self.cancelled = threading.Event()

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

    assert await asyncio.to_thread(chat_completion.started.wait, 1)
    await test_http_client.aclose()

    assert await asyncio.to_thread(chat_completion.cancelled.wait, 1)
    assert chat_completion.is_cancelled

    with contextlib.suppress(httpx.ReadError):
        await task


class EndlessApp(ChatCompletion):
    def __init__(self) -> None:
        self.finished = False

    async def chat_completion(self, request, response) -> None:
        try:
            with response.create_single_choice() as choice:
                while True:
                    choice.append_content("x")
                    await asyncio.sleep(0)
        finally:
            self.finished = True


@pytest.mark.parametrize(
    "heartbeat_interval", [None, 60], ids=["no-heartbeat", "heartbeat"]
)
@pytest.mark.parametrize("chunks", [0, 1], ids=["before-start", "mid-stream"])
async def test_impl_stops_when_the_client_leaves(
    heartbeat_interval: float | None, chunks: int
) -> None:
    impl = EndlessApp()
    app = DIALApp().add_chat_completion(
        "app", impl, heartbeat_interval=heartbeat_interval
    )

    await serve_to_a_leaving_client(
        app,
        "/openai/deployments/app/chat/completions",
        {"messages": [{"role": "user", "content": "hello"}], "stream": True},
        {"api-key": "dummy-key"},
        chunks=chunks,
    )

    assert impl.finished
