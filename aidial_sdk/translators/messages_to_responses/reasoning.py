from typing import Literal

from anthropic.types import RedactedThinkingBlock, ThinkingBlock
from anthropic.types.beta import (
    BetaRedactedThinkingBlockParam,
    BetaThinkingBlockParam,
)
from openai.types.responses import (
    ResponseReasoningItem,
    ResponseReasoningItemParam,
)
from pydantic import BaseModel, ConfigDict, ValidationError

from aidial_sdk.utils.logging import logger as log


class _EncryptedReasoning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[2]
    id: str
    encrypted_content: str


class _Signature(BaseModel):
    """The encrypted reasoning item carried by an Anthropic thinking block
    to be replayed in the next turn."""

    model_config = ConfigDict(extra="forbid")

    dial_translator_reasoning_wrapper: _EncryptedReasoning


def to_signature(item: ResponseReasoningItem) -> str | None:
    if not item.encrypted_content:
        return None
    reasoning = _EncryptedReasoning(
        version=2, id=item.id, encrypted_content=item.encrypted_content
    )
    return _Signature(
        dial_translator_reasoning_wrapper=reasoning
    ).model_dump_json()


def to_anthropic_thinking_block(
    item: ResponseReasoningItem,
) -> ThinkingBlock | RedactedThinkingBlock | None:
    text = "\n\n".join(
        part.text
        for part in [*item.summary, *(item.content or [])]
        if part.text
    )
    signature = to_signature(item)
    if text:
        return ThinkingBlock(
            type="thinking", thinking=text, signature=signature or ""
        )
    if signature:
        return RedactedThinkingBlock(type="redacted_thinking", data=signature)
    return None


def to_reasoning_item(
    block: BetaThinkingBlockParam | BetaRedactedThinkingBlockParam,
) -> ResponseReasoningItemParam | None:
    match block["type"]:
        case "thinking":
            signature, text = block["signature"], block["thinking"]
        case "redacted_thinking":
            signature, text = block["data"], ""

    try:
        reasoning = _Signature.model_validate_json(
            signature
        ).dial_translator_reasoning_wrapper
    except ValidationError:
        # E.g. a Claude signature, which another provider can't verify
        log.debug(
            "Dropping a thinking block: its signature isn't a reasoning item "
            "of the Responses API"
        )
        return None

    return {
        "type": "reasoning",
        "id": reasoning.id,
        "encrypted_content": reasoning.encrypted_content,
        "summary": [{"type": "summary_text", "text": text}] if text else [],
    }
