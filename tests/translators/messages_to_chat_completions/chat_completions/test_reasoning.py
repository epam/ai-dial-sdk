from typing import cast

import pytest
from anthropic.types.beta.message_create_params import MessageCreateParams

from aidial_sdk.translators.messages_to_chat_completions.chat_completions.reasoning import (
    resolve_effort,
)
from aidial_sdk.translators.messages_to_chat_completions.errors import (
    AnthropicErrorType,
    AnthropicHTTPError,
)


def request(body: dict[str, object]) -> MessageCreateParams:
    return cast(
        MessageCreateParams,
        {"model": "foobar", "max_tokens": 100, "messages": [], **body},
    )


def intent(body: dict[str, object]):
    return resolve_effort(request(body))


def system_turn(effort: str | None, **fields: object) -> dict[str, object]:
    config: dict[str, object] = {} if effort is None else {"effort": effort}
    return {
        "role": "system",
        "content": "",
        "output_config": config,
        **fields,
    }


@pytest.mark.parametrize("effort", ["low", "medium", "high", "xhigh", "max"])
def test_explicit_effort_is_preserved(effort: str) -> None:
    assert (
        intent(
            {
                "output_config": {"effort": effort},
                "thinking": {"type": "adaptive"},
            }
        )
        == effort
    )


def test_disabled_thinking_takes_precedence() -> None:
    assert (
        intent(
            {
                "thinking": {"type": "disabled"},
                "output_config": {"effort": "high"},
            }
        )
        == "none"
    )


def test_omission_leaves_deployment_default() -> None:
    assert intent({}) is None


def test_adaptive_thinking_leaves_deployment_default() -> None:
    assert intent({"thinking": {"type": "adaptive"}}) is None


@pytest.mark.parametrize("budget", [1024, 8000, 8001, 24000, 24001, 999999])
def test_budget_does_not_choose_effort(budget: int) -> None:
    assert (
        intent({"thinking": {"type": "enabled", "budget_tokens": budget}})
        is None
    )
    assert (
        intent(
            {
                "thinking": {"type": "enabled", "budget_tokens": budget},
                "output_config": {"effort": "low"},
            }
        )
        == "low"
    )


def test_the_last_visible_system_turn_effort_wins_over_the_request() -> None:
    assert (
        intent(
            {
                "messages": [
                    system_turn("low"),
                    {"role": "user", "content": "hi"},
                    system_turn("max"),
                ],
                "output_config": {"effort": "medium"},
            }
        )
        == "max"
    )


def test_a_cleared_system_turn_effort_is_not_visible() -> None:
    assert (
        intent(
            {
                "messages": [
                    system_turn("low"),
                    system_turn("max", clear_at="next_user_message"),
                    {"role": "user", "content": "hi"},
                ],
            }
        )
        == "low"
    )


def test_a_system_turn_without_effort_falls_back_to_the_request() -> None:
    assert (
        intent(
            {
                "messages": [system_turn("low"), system_turn(None)],
                "output_config": {"effort": "high"},
            }
        )
        == "high"
    )


def test_disabled_thinking_overrides_a_system_turn_effort() -> None:
    assert (
        intent(
            {
                "messages": [system_turn("max")],
                "thinking": {"type": "disabled"},
            }
        )
        == "none"
    )


@pytest.mark.parametrize(
    "body",
    [
        {"output_config": {"effort": "extreme"}},
        {"messages": [system_turn("extreme")]},
    ],
)
def test_an_unknown_effort_is_rejected(body: dict[str, object]) -> None:
    with pytest.raises(AnthropicHTTPError) as error:
        intent(body)
    assert error.value.error_type == AnthropicErrorType.INVALID_REQUEST
