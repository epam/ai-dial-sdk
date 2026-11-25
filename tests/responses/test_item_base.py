import pytest

from aidial_sdk.responses._context import _ResponseContext
from aidial_sdk.responses._item_base import _Builder, _ItemBuilder, _PartBuilder
from aidial_sdk.responses.models import ResponseCustomToolCall, ResponseObject
from tests.responses.conftest import raises_runtime_error


def _context(*, stream: bool = True) -> _ResponseContext:
    response_object = ResponseObject(
        id="resp_1", created_at=1700000000, model="m"
    )
    return _ResponseContext(response_object, stream=stream)


class _Stub(_Builder):
    """Records its enter and exit events instead of emitting them."""

    _kind = "stub"

    def __init__(self, log: list[str], name: str, parent: "_Stub | None"):
        super().__init__(_context(), parent)
        self._log = log
        self._name = name
        self._on_open()

    def _on_open(self) -> None:
        self._log.append(f"open {self._name}")

    def _on_close(self) -> None:
        self._log.append(f"close {self._name}")

    def child(self, name: str) -> "_Stub":
        return _Stub(self._log, name, parent=self)

    def touch(self) -> "_Stub":
        self._check_writable("touch")
        self._log.append(f"touch {self._name}")
        return self


def _root(log: list[str]) -> _Stub:
    return _Stub(log, "root", parent=None)


class _Boom(Exception):
    pass


def test_creation_opens():
    log = []
    root = _root(log)

    assert log == ["open root"]
    assert not root.closed


def test_entering_does_not_open_again():
    log = []

    with _root(log) as root:
        assert log == ["open root"]
        assert isinstance(root, _Stub)

    assert log == ["open root", "close root"]


def test_exit_closes_self_only():
    log = []
    root = _root(log)

    with root.child("child") as child:
        child.touch()

    assert child.closed
    assert not root.closed
    assert log == ["open root", "open child", "touch child", "close child"]


def test_close_cascades_to_ancestors():
    log = []
    root = _root(log)
    child = root.child("child")
    grandchild = child.child("grandchild")

    assert grandchild.close() is grandchild

    assert root.closed and child.closed and grandchild.closed
    assert log[-3:] == ["close grandchild", "close child", "close root"]


def test_close_stops_at_a_closed_ancestor():
    log = []
    root = _root(log)
    child = root.child("child")
    grandchild = child.child("grandchild")
    child._close_self()

    grandchild.close()

    assert not root.closed
    assert log[-2:] == ["close child", "close grandchild"]


def test_fluent_and_with_forms_agree():
    fluent: list[str] = []
    _root(fluent).child("child").touch().close()

    nested: list[str] = []
    with _root(nested) as root, root.child("child") as child:
        child.touch()

    assert fluent == nested


def test_close_inside_a_block_is_not_repeated_on_exit():
    log = []

    with _root(log) as root, root.child("child") as child:
        child.close()

    assert log == ["open root", "open child", "close child", "close root"]


def test_exception_propagates_and_leaves_builders_open():
    log = []
    root = _root(log)

    with pytest.raises(_Boom), root, root.child("child") as child:
        raise _Boom()

    assert not root.closed and not child.closed
    assert log == ["open root", "open child"]


def test_exit_never_swallows():
    root = _root([])

    assert root.__exit__(_Boom, _Boom(), None) is False
    assert root.__exit__(None, None, None) is False


def test_close_twice(caplog):
    root = _root([]).close()

    with raises_runtime_error(caplog, "Trying to close a closed stub"):
        root.close()


def test_write_to_closed(caplog):
    root = _root([]).close()

    with raises_runtime_error(caplog, "Trying to touch a closed stub"):
        root.touch()


class _StubItem(_ItemBuilder[ResponseCustomToolCall]):
    _kind = "stub item"

    def __init__(self, ctx: _ResponseContext, id: str):
        super().__init__(
            ctx, ResponseCustomToolCall(id=id, call_id="call_1", name="f")
        )
        self._on_open()

    def _on_close(self) -> None:
        self._emit_done()


class _StubPart(_PartBuilder):
    _kind = "stub part"

    def _on_open(self) -> None:
        pass

    def _on_close(self) -> None:
        pass


def _drain(ctx: _ResponseContext) -> list[dict]:
    drained = []
    while not ctx._queue.empty():
        drained.append(ctx._queue.get_nowait())
    return drained


def test_item_takes_output_index_and_place_on_creation():
    ctx = _context()
    first = _StubItem(ctx, "ctc_1")
    second = _StubItem(ctx, "ctc_2")

    assert (first.id, first.output_index) == ("ctc_1", 0)
    assert (second.id, second.output_index) == ("ctc_2", 1)
    assert ctx.response_object.output == [first._item, second._item]


def test_item_emits_added_on_creation_and_done_on_close():
    ctx = _context()
    item = _StubItem(ctx, "ctc_1")
    item.close()

    assert [(e["type"], e["output_index"]) for e in _drain(ctx)] == [
        ("response.output_item.added", 0),
        ("response.output_item.done", 0),
    ]


def test_part_inherits_item_bookkeeping():
    ctx = _context()
    _StubItem(ctx, "ctc_1")
    item = _StubItem(ctx, "ctc_2")
    part = _StubPart(item, index=3)

    assert (part._item_id, part._output_index, part._index) == ("ctc_2", 1, 3)

    part.close()

    assert item.closed
