import asyncio
from asyncio import exceptions
from typing import Optional, Set


class CancelScope:
    """
    Async context manager that enforces cancellation of all tasks created within its scope when either:
    1. the parent task has been cancelled or has thrown an exception or
    2. any of the tasks created within the scope has thrown an exception.
    """

    def __init__(self):
        self._tasks: Set[asyncio.Task] = set()
        self._on_completed_fut: Optional[asyncio.Future] = None
        self._cancelling: bool = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):

        cancelled_error = (
            exc if isinstance(exc, exceptions.CancelledError) else None
        )

        # If the parent task has thrown an exception, cancel all the tasks
        if exc_type is not None:
            self._cancel_tasks()

        while self._tasks:
            if self._on_completed_fut is None:
                self._on_completed_fut = asyncio.Future()

            # If the parent task was cancelled, cancel all the tasks
            try:
                await self._on_completed_fut
            except exceptions.CancelledError as ex:
                cancelled_error = ex
                self._cancel_tasks()

            self._on_completed_fut = None

        if cancelled_error:
            raise cancelled_error

    def create_task(self, coro):
        task = asyncio.create_task(coro)
        task.add_done_callback(self._on_task_done)
        self._tasks.add(task)
        return task

    def _cancel_tasks(self):
        if not self._cancelling:
            self._cancelling = True
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

        # If any of the tasks was cancelled, cancel all the tasks
        if task.exception() is not None:
            self._cancel_tasks()
