from typing import Self, TypeVar

from aidial_sdk.responses import events
from aidial_sdk.responses._context import _ResponseContext
from aidial_sdk.responses._ids import IMAGE_GENERATION_PREFIX, WEB_SEARCH_PREFIX
from aidial_sdk.responses._item_base import _ItemBuilder
from aidial_sdk.responses.models import (
    ImageGenerationCall,
    ResponseFunctionWebSearch,
    SearchAction,
    SearchSource,
    WebSearchAction,
)
from aidial_sdk.utils.errors import runtime_error

_ToolT = TypeVar("_ToolT", ResponseFunctionWebSearch, ImageGenerationCall)


class _ServerTool(_ItemBuilder[_ToolT]):
    """
    A server-side tool, whose item can state its own failure.
    On an exception it is closed with `status: "failed"` and without its
    terminal status event, since the protocol has no failure event for it.
    The exception is not swallowed.
    """

    def _fail_self(self) -> None:
        self._closed = True
        self._item.status = "failed"
        self._emit_done()


class WebSearch(_ServerTool[ResponseFunctionWebSearch]):
    _kind = "web search"

    def __init__(self, ctx: _ResponseContext):
        super().__init__(
            ctx, ResponseFunctionWebSearch(id=ctx.new_id(WEB_SEARCH_PREFIX))
        )
        self._on_open()

    def searching(
        self, *, query: str | None = None, queries: list[str] | None = None
    ) -> Self:
        """Sets `query` / `queries`, when given, on the `search` action."""
        self._check_writable("set the status of")

        if query is not None or queries is not None:
            action = self._search_action("set the query of")
            if query is not None:
                action.query = query
            if queries is not None:
                action.queries = queries

        self._item.status = "searching"
        self._ctx.emit(
            events.web_search_call_searching(
                item_id=self.id, output_index=self._output_index
            )
        )
        return self

    def set_action(self, action: WebSearchAction) -> Self:
        """No event: the action is carried by `output_item.done` only."""
        self._check_writable("set the action of")
        self._item.action = action
        return self

    def add_source(self, url: str) -> Self:
        """No event: appends to the sources of the `search` action."""
        self._check_writable("add a source to")

        action = self._search_action("add a source to")
        if action.sources is None:
            action.sources = []
        action.sources.append(SearchSource(url=url))
        return self

    def _search_action(self, action: str) -> SearchAction:
        if not isinstance(self._item.action, SearchAction):
            raise runtime_error(
                f"Trying to {action} a web search whose action is not a search"
            )
        return self._item.action

    def _on_open(self) -> None:
        super()._on_open()
        self._ctx.emit(
            events.web_search_call_in_progress(
                item_id=self.id, output_index=self._output_index
            )
        )

    def _on_close(self) -> None:
        self._item.status = "completed"
        self._ctx.emit(
            events.web_search_call_completed(
                item_id=self.id, output_index=self._output_index
            )
        )
        self._emit_done()


class ImageGeneration(_ServerTool[ImageGenerationCall]):
    _kind = "image generation"

    _partial_image_index: int

    def __init__(self, ctx: _ResponseContext):
        super().__init__(
            ctx, ImageGenerationCall(id=ctx.new_id(IMAGE_GENERATION_PREFIX))
        )
        self._partial_image_index = 0
        self._on_open()

    def generating(self) -> Self:
        self._check_writable("set the status of")

        self._item.status = "generating"
        self._ctx.emit(
            events.image_generation_call_generating(
                item_id=self.id, output_index=self._output_index
            )
        )
        return self

    def append_partial(self, b64: str) -> Self:
        """Partial images are stream-only: the item does not keep them."""
        self._check_writable("append a partial image to")

        self._ctx.emit(
            events.image_generation_call_partial_image(
                item_id=self.id,
                output_index=self._output_index,
                partial_image_index=self._partial_image_index,
                partial_image_b64=b64,
            )
        )
        self._partial_image_index += 1
        return self

    def set_result(self, b64: str) -> Self:
        """No event: the result is carried by `output_item.done` only."""
        self._check_writable("set the result of")
        self._item.result = b64
        return self

    def _on_open(self) -> None:
        super()._on_open()
        self._ctx.emit(
            events.image_generation_call_in_progress(
                item_id=self.id, output_index=self._output_index
            )
        )

    def _on_close(self) -> None:
        self._item.status = "completed"
        self._ctx.emit(
            events.image_generation_call_completed(
                item_id=self.id, output_index=self._output_index
            )
        )
        self._emit_done()
