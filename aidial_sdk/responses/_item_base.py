from abc import ABC, abstractmethod
from types import TracebackType
from typing import Any, ClassVar, Generic, Self, TypeVar

from aidial_sdk.responses import events
from aidial_sdk.responses._context import _ResponseContext
from aidial_sdk.responses.models import ResponseOutputItem
from aidial_sdk.utils.errors import runtime_error

_ItemT = TypeVar("_ItemT", bound=ResponseOutputItem)


class _Chunks:
    """
    The deltas of a string field of the snapshot, joined when the field
    is written: `+=` on the field would copy the whole string on every
    delta, quadratic in its length.
    """

    _chunks: list[str]

    def __init__(self) -> None:
        self._chunks = []

    def __bool__(self) -> bool:
        return any(self._chunks)

    def append(self, chunk: str) -> None:
        self._chunks.append(chunk)

    def join(self) -> str:
        text = "".join(self._chunks)
        self._chunks = [text]
        return text


class _Builder(ABC):
    """
    The open/close mechanics shared by every builder.

    A builder is opened by its own constructor, so the enter events are
    already emitted when `create_*` returns it; `with` only decides when it
    is closed.
    """

    _kind: ClassVar[str]

    _ctx: _ResponseContext
    _parent: "_Builder | None"
    _closed: bool

    def __init__(self, ctx: _ResponseContext, parent: "_Builder | None"):
        self._ctx = ctx
        self._parent = parent
        self._closed = False

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        # Unlike close(), leaves the ancestors to their own blocks.
        # Nothing follows the terminal event, e.g. when the block exits
        # after the response failed
        if not self._closed and not self._ctx.finished:
            if exc is None:
                self._close_self()
            else:
                self._fail_self()
        return False

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> Self:
        """
        Closes the builder, then its unclosed ancestors,
        which is what lets a fluent chain terminate.
        """
        if self._closed:
            raise runtime_error(f"Trying to close a closed {self._kind}")
        self._check_not_finished("close")

        self._close_self()
        if self._parent is not None and not self._parent._closed:
            self._parent.close()
        return self

    def _close_self(self) -> None:
        self._closed = True
        self._on_close()

    def _fail_self(self) -> None:
        """
        Records a failure: on an exception, and on the response failing.
        By default the builder is left open, since its exit events would
        claim the content finished normally, but what was written reaches
        the snapshot `response.failed` carries.
        """
        self._sync()

    def _sync(self) -> None:  # noqa: B027 -- empty on purpose
        """
        Writes the accumulated deltas into the snapshot: on close, and on
        a failure, before the snapshot is serialised.
        """

    def _check_writable(self, action: str) -> None:
        if self._closed:
            raise runtime_error(f"Trying to {action} a closed {self._kind}")
        self._check_not_finished(action)

    def _check_not_finished(self, action: str) -> None:
        # Nothing follows the terminal event, so a write after it is refused
        # rather than leaving the builder out of step with the response sent
        if self._ctx.finished:
            raise runtime_error(
                f"Trying to {action} a {self._kind} after end of generation"
            )

    @abstractmethod
    def _on_open(self) -> None:
        """
        Emits the builder's enter events. Every concrete builder calls it
        last in its `__init__`, once the state the events carry is set.
        """

    @abstractmethod
    def _on_close(self) -> None:
        """
        Finalises the builder's part of the snapshot and emits its exit events.
        """


class _ItemBuilder(_Builder, Generic[_ItemT]):
    """
    A builder of an output item. The item takes the next `output_index`
    and its place in `output[]` when the builder is created.
    """

    _item: _ItemT
    _output_index: int

    def __init__(self, ctx: _ResponseContext, item: _ItemT):
        super().__init__(ctx, parent=None)
        self._item = item
        self._output_index = ctx.next_output_index()
        ctx.response_object.output.append(item)

    @property
    def id(self) -> str:
        return self._item.id

    @property
    def output_index(self) -> int:
        return self._output_index

    def _on_open(self) -> None:
        self._ctx.emit(
            events.output_item_added(
                output_index=self._output_index, item=self._item
            )
        )

    def _set_incomplete(self) -> None:  # noqa: B027 -- a no-op by default
        """
        Records that an incomplete response cut the item off: called on
        each item still open when it ends, right before it's closed.
        Each item type states it as its schema allows; by default nothing
        is recorded, which is right only for an item with no `status`.
        """

    def _emit_done(self) -> None:
        self._ctx.emit(
            events.output_item_done(
                output_index=self._output_index, item=self._item
            )
        )


class _PartBuilder(_Builder):
    """
    A builder of a part of an output item: a content part at
    `content_index`, or a reasoning summary part at `summary_index`.
    """

    _item_id: str
    _output_index: int
    _index: int

    def __init__(self, parent: _ItemBuilder[Any], index: int):
        super().__init__(parent._ctx, parent=parent)
        self._item_id = parent.id
        self._output_index = parent.output_index
        self._index = index
