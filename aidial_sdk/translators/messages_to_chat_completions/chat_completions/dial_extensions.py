import re
from collections.abc import Mapping

from openai.types.chat.chat_completion_message import Annotation
from pydantic import ValidationError

from aidial_sdk.utils.logging import logger as log
from aidial_sdk.utils.pydantic import ExtraAllowModel

_REASONING_STAGE = re.compile(r"think|thought|reason", re.IGNORECASE)


class ClaudeMessageBlock(ExtraAllowModel):
    type: str | None = None
    thinking: str | None = None
    signature: str | None = None


class MessageState(ExtraAllowModel):
    claude_message_content: list[ClaudeMessageBlock] | None = None


class Stage(ExtraAllowModel):
    index: int | None = None
    name: str | None = None
    content: str | None = None


class CustomContent(ExtraAllowModel):
    stages: list[Stage] | None = None
    state: MessageState | None = None


class DialExtras(ExtraAllowModel):
    custom_content: CustomContent | None = None
    annotations: list[Annotation] | None = None


def parse_extras(model_extra: Mapping[str, object] | None) -> DialExtras:
    try:
        return DialExtras.model_validate(model_extra or {})
    except ValidationError as e:
        log.error(f"Failed to parse DIAL extension fields: {e}")
        return DialExtras()


def is_reasoning_stage(name: str | None) -> bool:
    return name is not None and bool(_REASONING_STAGE.search(name))


def get_claude_thinking_block(
    custom_content: CustomContent | None,
) -> ClaudeMessageBlock | None:
    state = custom_content.state if custom_content else None
    for block in (state.claude_message_content if state else None) or []:
        if block.type == "thinking" and block.thinking:
            return block
    return None


def get_dial_reasoning_content(custom_content: CustomContent | None) -> str:
    return "".join(
        stage.content or ""
        for stage in (custom_content.stages if custom_content else None) or []
        if is_reasoning_stage(stage.name)
    )
