import re
from dataclasses import dataclass
from typing import Literal

from openai.types.chat import ChatCompletionMessage
from openai.types.chat.chat_completion_chunk import ChoiceDelta

from aidial_sdk.translators.messages_to_chat_completions.chat_completions.dial_extensions import (
    CustomContent,
    parse_extras,
)

_Source = Literal["azure", "claude", "dial"]

_REASONING_STAGE = re.compile(r"think|thought|reason", re.IGNORECASE)


@dataclass
class ReasoningContent:
    content: str | None
    signature: str | None


class ReasoningContentProvider:
    """
    Reads the reasoning of a message, or of a stream of message chunks, from
    `reasoning_content`, the Claude state and the DIAL reasoning stages. They
    carry the same text, chunked differently: only the text none of them has
    delivered before is returned.
    """

    def __init__(self) -> None:
        # Every source is a prefix of the same text, so offsets suffice.
        self._returned = 0
        self._received: dict[_Source, int] = {
            "azure": 0,
            "claude": 0,
            "dial": 0,
        }
        self._reasoning_stages: set[int | None] = set()

    def get_reasoning_content(
        self, message: ChatCompletionMessage | ChoiceDelta
    ) -> ReasoningContent:
        custom_content = parse_extras(message.model_extra).custom_content
        thinking, signature = _get_claude_reasoning_content(custom_content)
        content = (
            self._unseen("azure", _get_azure_reasoning_content(message))
            + self._unseen("claude", thinking)
            + self._unseen("dial", self._dial_reasoning_content(custom_content))
        )
        return ReasoningContent(
            content=content or None,
            signature=signature or None,
        )

    def _unseen(self, source: _Source, text: str | None) -> str:
        text = text or ""
        start = self._received[source]
        self._received[source] += len(text)
        unseen = text[self._returned - start :]
        self._returned = max(self._returned, self._received[source])
        return unseen

    def _dial_reasoning_content(
        self, custom_content: CustomContent | None
    ) -> str:
        text = ""
        for stage in (custom_content.stages if custom_content else None) or []:
            # In a stream, only the first chunk of a stage carries its name.
            if _is_reasoning_stage(stage.name):
                self._reasoning_stages.add(stage.index)
            if stage.index in self._reasoning_stages:
                text += stage.content or ""
        return text


def _get_azure_reasoning_content(
    message: ChatCompletionMessage | ChoiceDelta,
) -> str | None:
    return (message.model_extra or {}).get("reasoning_content")


def _get_claude_reasoning_content(
    custom_content: CustomContent | None,
) -> tuple[str | None, str | None]:
    state = custom_content.state if custom_content else None
    for block in (state.claude_message_content if state else None) or []:
        if block.type == "thinking":
            return block.thinking, block.signature
    return None, None


def _is_reasoning_stage(name: str | None) -> bool:
    return name is not None and bool(_REASONING_STAGE.search(name))
