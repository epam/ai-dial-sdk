from typing import Optional

from aidial_sdk.chat_completion.choice_base import ChoiceBase
from aidial_sdk.chat_completion.chunks import FunctionCallChunk
from aidial_sdk.utils.errors import runtime_error


class FunctionCall:
    _choice: ChoiceBase

    def __init__(self, choice: ChoiceBase):
        self._choice = choice

    @classmethod
    def create_and_send(
        cls, choice: ChoiceBase, name: str, arguments: Optional[str]
    ) -> "FunctionCall":
        return cls(choice)._send_function_call(
            create=True, name=name, arguments=arguments
        )

    def append_arguments(self, arguments: str) -> "FunctionCall":
        return self._send_function_call(
            create=False, name=None, arguments=arguments
        )

    def _send_function_call(
        self, *, create: bool, name: Optional[str], arguments: Optional[str]
    ) -> "FunctionCall":
        if not self._choice.opened:
            raise runtime_error(
                "Trying to add function call to an unopened choice"
            )
        if self._choice.closed:
            raise runtime_error(
                "Trying to add function call to a closed choice"
            )
        if create and self._choice.has_function_call:
            raise runtime_error(
                "Trying to add function call to a choice which already has a function call"
            )

        self._choice.send_chunk(
            FunctionCallChunk(
                self._choice.index, name=name, arguments=arguments
            )
        )

        return self
