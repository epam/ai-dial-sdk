import json
from typing import Any, Self

from aidial_sdk.responses import events
from aidial_sdk.responses._context import _ResponseContext
from aidial_sdk.responses._ids import (
    CALL_PREFIX,
    CUSTOM_TOOL_CALL_PREFIX,
    FUNCTION_CALL_PREFIX,
)
from aidial_sdk.responses._item_base import _ItemBuilder
from aidial_sdk.responses.enums import ItemStatus
from aidial_sdk.responses.models import (
    ResponseCustomToolCall,
    ResponseFunctionToolCall,
)
from aidial_sdk.utils.errors import runtime_error


class FunctionCall(_ItemBuilder[ResponseFunctionToolCall]):
    _kind = "function call"

    _incomplete: bool

    def __init__(
        self, ctx: _ResponseContext, name: str, call_id: str | None = None
    ):
        super().__init__(
            ctx,
            ResponseFunctionToolCall(
                id=ctx.new_id(FUNCTION_CALL_PREFIX),
                call_id=call_id or ctx.new_id(CALL_PREFIX),
                name=name,
            ),
        )
        self._incomplete = False
        self._on_open()

    @property
    def call_id(self) -> str:
        return self._item.call_id

    def set_incomplete(self) -> Self:
        self._check_writable("set the status of")
        self._incomplete = True
        return self

    def append_arguments(self, arguments: str) -> Self:
        self._check_writable("append arguments to")

        self._item.arguments += arguments
        self._ctx.emit(
            events.function_call_arguments_delta(
                item_id=self.id,
                output_index=self._output_index,
                delta=arguments,
            )
        )
        return self

    def set_arguments(self, arguments: str | dict[str, Any]) -> Self:
        """Emits the arguments as a single delta; a dict is JSON-encoded."""
        self._check_writable("set the arguments of")
        if self._item.arguments:
            raise runtime_error(
                f"Trying to set the arguments of a {self._kind} "
                "that already has arguments"
            )

        if isinstance(arguments, dict):
            arguments = json.dumps(arguments)
        return self.append_arguments(arguments)

    def _on_close(self) -> None:
        self._ctx.emit(
            events.function_call_arguments_done(
                item_id=self.id,
                output_index=self._output_index,
                name=self._item.name,
                arguments=self._item.arguments,
            )
        )
        self._item.status = (
            ItemStatus.INCOMPLETE if self._incomplete else ItemStatus.COMPLETED
        )
        self._emit_done()


class CustomToolCall(_ItemBuilder[ResponseCustomToolCall]):
    # NOTE: the item has no `status`, hence no set_incomplete()
    _kind = "custom tool call"

    def __init__(
        self, ctx: _ResponseContext, name: str, call_id: str | None = None
    ):
        super().__init__(
            ctx,
            ResponseCustomToolCall(
                id=ctx.new_id(CUSTOM_TOOL_CALL_PREFIX),
                call_id=call_id or ctx.new_id(CALL_PREFIX),
                name=name,
            ),
        )
        self._on_open()

    @property
    def call_id(self) -> str:
        return self._item.call_id

    def append_input(self, input: str) -> Self:
        self._check_writable("append input to")

        self._item.input += input
        self._ctx.emit(
            events.custom_tool_call_input_delta(
                item_id=self.id,
                output_index=self._output_index,
                delta=input,
            )
        )
        return self

    def set_input(self, input: str) -> Self:
        """Emits the input as a single delta."""
        self._check_writable("set the input of")
        if self._item.input:
            raise runtime_error(
                f"Trying to set the input of a {self._kind} "
                "that already has input"
            )

        return self.append_input(input)

    def _on_close(self) -> None:
        self._ctx.emit(
            events.custom_tool_call_input_done(
                item_id=self.id,
                output_index=self._output_index,
                input=self._item.input,
            )
        )
        self._emit_done()
