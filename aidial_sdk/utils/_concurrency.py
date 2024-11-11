import asyncio
from typing import Optional, Set


class TaskGroup:
    """
    [TaskGroup](https://docs.python.org/3/library/asyncio-task.html#asyncio.TaskGroup) was introduced in Python 3.11.
    This class is a simplified copy of [TaskGroup](https://github.com/python/cpython/blob/3.13/Lib/asyncio/taskgroups.py) from asyncio.

    The most important feature we are interested in is automatic propagation of cancellation error to all tasks in the group (see the exist method).
    """

    _tasks: Set[asyncio.Task]
    _on_completed_fut: Optional[asyncio.Future]

    def __init__(self) -> None:
        self._tasks = set()
        self._on_completed_fut = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, et, exc, tb) -> None:
        if isinstance(exc, asyncio.CancelledError):
            self._abort()

        while self._tasks:
            if self._on_completed_fut is None:
                self._on_completed_fut = (
                    asyncio.get_event_loop().create_future()
                )

            try:
                await self._on_completed_fut
            except asyncio.CancelledError:
                self._abort()

    def _abort(self):
        for t in self._tasks:
            t.cancel()

    def create_task(self, coro):
        task = asyncio.create_task(coro)

        if task.done():
            self._on_task_done(task)
        else:
            task.add_done_callback(self._on_task_done)

        self._tasks.add(task)

        return task

    def _on_task_done(self, task):
        self._tasks.discard(task)

        if self._on_completed_fut is not None and not self._tasks:
            if not self._on_completed_fut.done():
                self._on_completed_fut.set_result(True)
