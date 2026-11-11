from collections.abc import Callable
from typing import Literal, Self

from aidial_sdk.responses import events
from aidial_sdk.responses._context import _ResponseContext
from aidial_sdk.responses._ids import MESSAGE_PREFIX
from aidial_sdk.responses._item_base import _ItemBuilder, _PartBuilder
from aidial_sdk.responses.enums import ItemStatus, MessagePhase
from aidial_sdk.responses.models import (
    Annotation,
    Logprob,
    ResponseOutputMessage,
    ResponseOutputRefusal,
    ResponseOutputText,
    UrlCitation,
)
from aidial_sdk.utils._content_stream import ContentStream


class _ContentReceiver:
    """Adapts a builder's append method to what `ContentStream` expects."""

    def __init__(self, append: Callable[[str], object]):
        self._append = append

    def append_content(self, content: str) -> None:
        self._append(content)


class TextPart(_PartBuilder):
    _kind = "text part"

    _part: ResponseOutputText
    _pending_logprobs: list[Logprob]

    def __init__(self, message: "Message"):
        content = message._item.content
        super().__init__(message, index=len(content))
        self._part = ResponseOutputText(logprobs=[])
        self._pending_logprobs = []
        content.append(self._part)
        self._on_open()

    def append(self, text: str) -> Self:
        self._check_writable("append text to")

        self._part.text += text
        self._emit_delta(text)
        return self

    def add_annotation(self, annotation: Annotation) -> Self:
        self._check_writable("add an annotation to")

        self._part.annotations.append(annotation)
        self._ctx.emit(
            events.output_text_annotation_added(
                item_id=self._item_id,
                output_index=self._output_index,
                content_index=self._index,
                annotation_index=len(self._part.annotations) - 1,
                annotation=annotation,
            )
        )
        return self

    def add_url_citation(
        self,
        url: str,
        *,
        title: str | None = None,
        start_index: int | None = None,
        end_index: int | None = None,
    ) -> Self:
        """
        Adds a `url_citation` annotation.

        The protocol requires `title`, `start_index` and `end_index`, so the
        omitted ones are filled in: `title` with `""`, and the indices with
        the range of the text appended so far, `(0, len(text))`.
        """
        return self.add_annotation(
            UrlCitation(
                url=url,
                title="" if title is None else title,
                start_index=0 if start_index is None else start_index,
                end_index=(
                    len(self._part.text) if end_index is None else end_index
                ),
            )
        )

    def add_logprobs(self, logprobs: list[Logprob]) -> Self:
        """
        No event: the logprobs ride the next `append`,
        or an empty delta on close if no `append` follows.
        """
        self._check_writable("add logprobs to")

        # In place: a per-token call would make copying quadratic
        if self._part.logprobs is None:
            self._part.logprobs = []
        self._part.logprobs.extend(logprobs)
        self._pending_logprobs += logprobs
        return self

    @property
    def content_stream(self) -> ContentStream:
        return ContentStream(_ContentReceiver(self.append))

    def _emit_delta(self, text: str) -> None:
        logprobs, self._pending_logprobs = self._pending_logprobs, []
        self._ctx.emit(
            events.output_text_delta(
                item_id=self._item_id,
                output_index=self._output_index,
                content_index=self._index,
                delta=text,
                logprobs=logprobs,
            )
        )

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
        if self._pending_logprobs:
            self._emit_delta("")
        self._ctx.emit(
            events.output_text_done(
                item_id=self._item_id,
                output_index=self._output_index,
                content_index=self._index,
                text=self._part.text,
                logprobs=self._part.logprobs or [],
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


class RefusalPart(_PartBuilder):
    _kind = "refusal part"

    _part: ResponseOutputRefusal

    def __init__(self, message: "Message"):
        content = message._item.content
        super().__init__(message, index=len(content))
        self._part = ResponseOutputRefusal()
        content.append(self._part)
        self._on_open()

    def append(self, refusal: str) -> Self:
        self._check_writable("append refusal to")

        self._part.refusal += refusal
        self._ctx.emit(
            events.refusal_delta(
                item_id=self._item_id,
                output_index=self._output_index,
                content_index=self._index,
                delta=refusal,
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
            events.refusal_done(
                item_id=self._item_id,
                output_index=self._output_index,
                content_index=self._index,
                refusal=self._part.refusal,
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


_Phase = MessagePhase | Literal["commentary", "final_answer"]


class Message(_ItemBuilder[ResponseOutputMessage]):
    _kind = "message"

    _open_part: TextPart | RefusalPart | None
    _incomplete: bool

    def __init__(self, ctx: _ResponseContext, phase: _Phase | None = None):
        super().__init__(
            ctx,
            ResponseOutputMessage(
                id=ctx.new_id(MESSAGE_PREFIX),
                phase=None if phase is None else MessagePhase(phase),
            ),
        )
        self._open_part = None
        self._incomplete = False
        self._on_open()

    def set_incomplete(self) -> Self:
        self._check_writable("set the status of")
        self._incomplete = True
        return self

    def set_phase(self, phase: _Phase) -> Self:
        """
        No event: the phase reaches `output_item.done` and the snapshot only.
        A phase `output_item.added` should carry goes to `create_message`.
        """
        self._check_writable("set the phase of")
        self._item.phase = MessagePhase(phase)
        return self

    def append_text(self, text: str) -> Self:
        """Appends to the open text part, opening one if there is none."""
        self._check_writable("append text to")

        part = self._open_part
        if not isinstance(part, TextPart) or part.closed:
            part = self.create_text()
        part.append(text)
        return self

    def append_refusal(self, refusal: str) -> Self:
        """Appends to the open refusal part, opening one if there is none."""
        self._check_writable("append refusal to")

        part = self._open_part
        if not isinstance(part, RefusalPart) or part.closed:
            part = self.create_refusal()
        part.append(refusal)
        return self

    @property
    def content_stream(self) -> ContentStream:
        return ContentStream(_ContentReceiver(self.append_text))

    def create_text(self) -> TextPart:
        self._check_writable("create a text part in")
        self._close_open_part()
        part = self._open_part = TextPart(self)
        return part

    def create_refusal(self) -> RefusalPart:
        self._check_writable("create a refusal part in")
        self._close_open_part()
        part = self._open_part = RefusalPart(self)
        return part

    def _close_open_part(self) -> None:
        # Opening a content part closes the one still open
        if self._open_part is not None and not self._open_part.closed:
            self._open_part._close_self()

    def _on_close(self) -> None:
        self._close_open_part()
        self._item.status = (
            ItemStatus.INCOMPLETE if self._incomplete else ItemStatus.COMPLETED
        )
        self._emit_done()
