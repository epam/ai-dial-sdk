import asyncio

from aidial_sdk.responses import events
from aidial_sdk.responses._ids import new_id
from aidial_sdk.responses.events import Event
from aidial_sdk.responses.models import ResponseObject


class _ResponseContext:
    """
    The state shared by the response and all of its builders: the response
    object, the event queue, the sequence numbers, the output indices and
    the ids.
    """

    response_object: ResponseObject
    stream: bool

    _queue: asyncio.Queue[Event]
    _sequence_number: int
    _output_index: int
    _generation_started: bool
    _finished: bool

    def __init__(self, response_object: ResponseObject, stream: bool):
        self.response_object = response_object
        self.stream = stream

        self._queue = asyncio.Queue()
        self._sequence_number = 0
        self._output_index = 0
        self._generation_started = False
        self._finished = False

    def emit(self, event: Event) -> None:
        """
        Assigns the next `sequence_number` and enqueues the event.

        A no-op in block mode, so that a sequence number is only consumed
        by an event that is actually emitted, and after the terminal event,
        so that nothing follows it: e.g. a builder closed by its block after
        the response failed.
        """
        if not self.stream or self._finished:
            return

        event["sequence_number"] = self._sequence_number
        self._sequence_number += 1
        self._queue.put_nowait(event)

    @property
    def generation_started(self) -> bool:
        return self._generation_started

    @property
    def finished(self) -> bool:
        return self._finished

    def start_generation(self) -> None:
        """
        Emits `response.created` and `response.in_progress`, once.

        Called right before the first event the handler produces, rather than
        before the handler runs: the response id, model and creation time
        the handler sets until then reach every lifecycle event.
        """
        if self._generation_started:
            return

        self._generation_started = True
        self.emit(events.response_created(response=self.response_object))
        self.emit(events.response_in_progress(response=self.response_object))

    def finish(self, terminal_event: Event) -> None:
        """Emits the terminal event, the last one the response emits."""
        self.emit(terminal_event)
        self._finished = True

    def next_output_index(self) -> int:
        index = self._output_index
        self._output_index += 1
        return index

    def new_id(self, prefix: str) -> str:
        return new_id(prefix)
