from anthropic.types.beta.message_create_params import MessageCreateParams
from openai.types.shared import ReasoningEffort
from pydantic import TypeAdapter, ValidationError

from aidial_sdk.translators.messages_to_chat_completions.chat_completions.system_turns import (
    visible_messages,
)
from aidial_sdk.translators.messages_to_chat_completions.errors import (
    AnthropicErrorType,
    AnthropicHTTPError,
)
from aidial_sdk.utils.logging import logger as log

_EFFORT = TypeAdapter(ReasoningEffort)


def resolve_effort(req: MessageCreateParams) -> ReasoningEffort:
    thinking = req.get("thinking")
    if thinking and thinking["type"] == "disabled":
        return "none"
    if thinking and thinking["type"] == "enabled":
        log.debug(
            "Dropping thinking.budget_tokens: no Chat Completions equivalent"
        )
    # Token budgets and qualitative effort levels have no protocol-defined
    # conversion. Leave the target's default unless effort is explicit.
    effort = _system_turn_effort(req) or (req.get("output_config") or {}).get(
        "effort"
    )
    try:
        return _EFFORT.validate_python(effort)
    except ValidationError:
        raise AnthropicHTTPError(
            AnthropicErrorType.INVALID_REQUEST,
            f"Cannot convert Anthropic Messages API reasoning effort {effort} "
            "to OpenAI Chat Completions API reasoning effort",
        ) from None


def _system_turn_effort(req: MessageCreateParams) -> str | None:
    system_turns = [
        message
        for message in visible_messages(req["messages"])
        if message["role"] == "system"
    ]
    if not system_turns:
        return None
    return (system_turns[-1].get("output_config") or {}).get("effort")
