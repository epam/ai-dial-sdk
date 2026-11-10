from typing import Self

from aidial_sdk.responses import events
from aidial_sdk.responses._context import _ResponseContext
from aidial_sdk.responses._ids import REASONING_PREFIX
from aidial_sdk.responses._item_base import _ItemBuilder, _PartBuilder
from aidial_sdk.responses.enums import ItemStatus
from aidial_sdk.responses.models import (
    ReasoningContent,
    ReasoningSummary,
    ResponseReasoningItem,
)


class SummaryPart(_PartBuilder):
    """`summary[summary_index]` of a reasoning item; not a content part."""

    _kind = "summary part"

    _part: ReasoningSummary
    _incomplete: bool

    def __init__(self, reasoning: "Reasoning"):
        summary = reasoning._item.summary
        super().__init__(reasoning, index=len(summary))
        self._part = ReasoningSummary()
        self._incomplete = False
        summary.append(self._part)
        self._on_open()

    def append(self, text: str) -> Self:
        self._check_writable("append text to")

        self._part.text += text
        self._ctx.emit(
            events.reasoning_summary_text_delta(
                item_id=self._item_id,
                output_index=self._output_index,
                summary_index=self._index,
                delta=text,
            )
        )
        return self

    def set_incomplete(self) -> Self:
        """No event: sets `status` on `reasoning_summary_part.done`."""
        self._check_writable("set the status of")
        self._incomplete = True
        return self

    def _on_open(self) -> None:
        self._ctx.emit(
            events.reasoning_summary_part_added(
                item_id=self._item_id,
                output_index=self._output_index,
                summary_index=self._index,
                part=self._part,
            )
        )

    def _on_close(self) -> None:
        self._ctx.emit(
            events.reasoning_summary_text_done(
                item_id=self._item_id,
                output_index=self._output_index,
                summary_index=self._index,
                text=self._part.text,
            )
        )
        self._ctx.emit(
            events.reasoning_summary_part_done(
                item_id=self._item_id,
                output_index=self._output_index,
                summary_index=self._index,
                part=self._part,
                incomplete=self._incomplete,
            )
        )


class ReasoningTextPart(_PartBuilder):
    """`content[content_index]` of a reasoning item."""

    _kind = "reasoning text part"

    _part: ReasoningContent

    def __init__(self, reasoning: "Reasoning"):
        if reasoning._item.content is None:
            reasoning._item.content = []
        content = reasoning._item.content
        super().__init__(reasoning, index=len(content))
        self._part = ReasoningContent()
        content.append(self._part)
        self._on_open()

    def append(self, text: str) -> Self:
        self._check_writable("append text to")

        self._part.text += text
        self._ctx.emit(
            events.reasoning_text_delta(
                item_id=self._item_id,
                output_index=self._output_index,
                content_index=self._index,
                delta=text,
            )
        )
        return self

    def _on_open(self) -> None:
        self._ctx.emit(
            events.content_part_added(
                item_id=self._item_id,
                output_index=self._output_index,
                content_index=self._index,
                part=self._part,
            )
        )

    def _on_close(self) -> None:
        self._ctx.emit(
            events.reasoning_text_done(
                item_id=self._item_id,
                output_index=self._output_index,
                content_index=self._index,
                text=self._part.text,
            )
        )
        self._ctx.emit(
            events.content_part_done(
                item_id=self._item_id,
                output_index=self._output_index,
                content_index=self._index,
                part=self._part,
            )
        )


class Reasoning(_ItemBuilder[ResponseReasoningItem]):
    _kind = "reasoning item"

    # `summary[]` and `content[]` have independent indices,
    # but one open part, closed by the next event on the item
    _open_part: SummaryPart | ReasoningTextPart | None
    _incomplete: bool

    def __init__(self, ctx: _ResponseContext):
        super().__init__(
            ctx, ResponseReasoningItem(id=ctx.new_id(REASONING_PREFIX))
        )
        self._open_part = None
        self._incomplete = False
        self._on_open()

    def set_incomplete(self) -> Self:
        self._check_writable("set the status of")
        self._incomplete = True
        return self

    def set_encrypted_content(self, encrypted_content: str) -> Self:
        """No event: the content is carried by `output_item.done` only."""
        self._check_writable("set the encrypted content of")
        self._item.encrypted_content = encrypted_content
        return self

    def append_summary(self, text: str) -> Self:
        """Appends to the open summary part, opening one if there is none."""
        self._check_writable("append summary to")

        part = self._open_part
        if not isinstance(part, SummaryPart) or part.closed:
            part = self.create_summary()
        part.append(text)
        return self

    def append_text(self, text: str) -> Self:
        """Appends to the open text part, opening one if there is none."""
        self._check_writable("append text to")

        part = self._open_part
        if not isinstance(part, ReasoningTextPart) or part.closed:
            part = self.create_text()
        part.append(text)
        return self

    def create_summary(self) -> SummaryPart:
        self._check_writable("create a summary part in")
        self._close_open_part()
        part = self._open_part = SummaryPart(self)
        return part

    def create_text(self) -> ReasoningTextPart:
        self._check_writable("create a text part in")
        self._close_open_part()
        part = self._open_part = ReasoningTextPart(self)
        return part

    def _close_open_part(self) -> None:
        # Opening a part closes the one still open, in either array
        if self._open_part is not None and not self._open_part.closed:
            self._open_part._close_self()

    def _on_close(self) -> None:
        self._close_open_part()
        self._item.status = (
            ItemStatus.INCOMPLETE if self._incomplete else ItemStatus.COMPLETED
        )
        self._emit_done()
