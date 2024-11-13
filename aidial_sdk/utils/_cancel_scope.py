import asyncio
from asyncio import events, exceptions


class CancelScope:
    """
    Async context manager that enforces cancellation of all tasks created created within the scope when either:
    1. the parent thread has been cancelled or
    2. any of the tasks created within the scope have thrown an exception.
    """

    def __init__(self):
        self._aborting = False
        self._loop = events.get_running_loop()
        self._tasks = set()
        self._on_completed_fut = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, et, exc, tb):

        cancellation_error = exc if et is exceptions.CancelledError else None

        if et is not None:
            self._abort()

        while self._tasks:
            if self._on_completed_fut is None:
                self._on_completed_fut = asyncio.Future()

            try:
                await self._on_completed_fut
            except exceptions.CancelledError as ex:
                cancellation_error = ex
                self._abort()

            self._on_completed_fut = None

        assert not self._tasks

        if cancellation_error:
            raise cancellation_error

    def create_task(self, coro):
        task = asyncio.create_task(coro)
        task.add_done_callback(self._on_task_done)
        self._tasks.add(task)
        return task

    def _abort(self):
        if not self._aborting:
            self._aborting = True
            for t in self._tasks:
                if not t.done():
                    t.cancel()

    def _on_task_done(self, task):
        self._tasks.discard(task)

        if (
            self._on_completed_fut is not None
            and not self._on_completed_fut.done()
            and not self._tasks
        ):
            self._on_completed_fut.set_result(True)

        if task.exception() is not None:
            self._abort()
