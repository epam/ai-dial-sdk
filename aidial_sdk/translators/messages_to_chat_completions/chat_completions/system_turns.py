from collections.abc import Iterable
from typing import Literal, cast

from anthropic.types.beta import BetaMessageParam, BetaOutputConfigParam


class MessageParam(BetaMessageParam, total=False):
    # anthropic>=1.0 types these system-turn fields, but aidial-adapter-anthropic
    # pins anthropic<1.
    clear_at: Literal["next_user_message", "never"] | None
    output_config: BetaOutputConfigParam | None


def visible_messages(
    messages: Iterable[BetaMessageParam],
) -> list[MessageParam]:
    visible: list[MessageParam] = []
    later_user = False
    for message in reversed(cast(list[MessageParam], list(messages))):
        if message["role"] == "user":
            later_user = True
        elif later_user and message.get("clear_at") == "next_user_message":
            continue
        visible.append(message)
    visible.reverse()
    return visible
