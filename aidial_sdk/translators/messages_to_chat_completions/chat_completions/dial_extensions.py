from collections.abc import Mapping

from openai.types.chat.chat_completion_message import Annotation
from pydantic import ValidationError

from aidial_sdk.utils.logging import logger as log
from aidial_sdk.utils.pydantic import ExtraAllowModel


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
