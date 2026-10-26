"""
An event loop whose clock fast-forwards to the next timer instead of
sleeping until it comes due.

Tests for timer-driven behaviour (heartbeats, timeouts, cancellation) keep
their original delays - and therefore their original semantics, since only
the *ratios* between the delays matter - but no longer pay for them in
wall-clock time.

Mark a test with `@pytest.mark.virtual_clock` to opt in; run with
`TESTS_REAL_CLOCK=1` to put every such test back on the real clock.

Only usable for loops that don't wait on real I/O: skipping ahead while a
socket read is in flight would make the timer win a race it shouldn't.
"""

import asyncio
import os
from typing import Any


class VirtualClockEventLoop(asyncio.SelectorEventLoop):
    _offset: float = 0.0

    def time(self) -> float:
        return super().time() + self._offset

    def _run_once(self) -> None:
        # Private asyncio internals, not described by the type stubs.
        loop: Any = self

        # Nothing to run right now, so instead of idling until the earliest
        # timer comes due, move the clock to it and let it fire immediately.
        if not loop._ready and loop._scheduled:
            self._offset += max(0.0, loop._scheduled[0]._when - self.time())

        super()._run_once()  # type: ignore[misc]


class VirtualClockEventLoopPolicy(asyncio.DefaultEventLoopPolicy):
    def new_event_loop(self) -> asyncio.AbstractEventLoop:
        return VirtualClockEventLoop()


def is_enabled() -> bool:
    return not os.getenv("TESTS_REAL_CLOCK")


def backend_options() -> dict[str, Any]:
    """
    anyio options making a test client's application loop follow the clock of
    the test that creates it, so that opting in stays a single marker on the
    test instead of an argument threaded through every helper.
    """
    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        return {}

    if isinstance(running_loop, VirtualClockEventLoop):
        return {"loop_factory": VirtualClockEventLoop}
    return {}
