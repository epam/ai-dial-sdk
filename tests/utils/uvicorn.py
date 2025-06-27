import asyncio
import socket
import threading
from contextlib import asynccontextmanager

import uvicorn


def get_free_port():
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@asynccontextmanager
async def run_uvicorn_in_thread(app, host="127.0.0.1", port=None):
    port = port or get_free_port()
    config = uvicorn.Config(
        app, host=host, port=port, log_level="warning", loop="asyncio"
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for server to actually start
    while not server.started:
        await asyncio.sleep(0.1)

    try:
        yield f"http://{host}:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=3)
