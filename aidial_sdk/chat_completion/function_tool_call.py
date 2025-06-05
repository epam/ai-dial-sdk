from typing import Literal, Optional

from aidial_sdk.chat_completion.choice_base import ChoiceBase
from aidial_sdk.chat_completion.chunks import FunctionToolCallChunk
from aidial_sdk.utils.errors import runtime_error


class FunctionToolCall:
    _choice: ChoiceBase
    _index: int

    def __init__(self, choice: ChoiceBase, index: int):
        self._choice = choice
        self._index = index

    @classmethod
    def create_and_send(
        cls,
        choice: ChoiceBase,
        index: int,
        id: str,
        name: str,
        arguments: Optional[str],
    ) -> "FunctionToolCall":
        return cls(choice, index)._send_tool_call(
            id=id, type="function", name=name, arguments=arguments
        )

    def append_arguments(self, arguments: str) -> "FunctionToolCall":
        return self._send_tool_call(
            id=None, type=None, name=None, arguments=arguments
        )

    def _send_tool_call(
        self,
        *,
        id: Optional[str],
        type: Optional[Literal["function"]],
        name: Optional[str],
        arguments: Optional[str],
    ) -> "FunctionToolCall":
        if not self._choice.opened:
            raise runtime_error("Trying to add tool call to an unopened choice")
        if self._choice.closed:
            raise runtime_error("Trying to add tool call to a closed choice")

        self._choice.send_chunk(
            FunctionToolCallChunk(
                self._choice.index,
                self._index,
                type=type,
                id=id,
                name=name,
                arguments=arguments,
            )
        )

        return self
