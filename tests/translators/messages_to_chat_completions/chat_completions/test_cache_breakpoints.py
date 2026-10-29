from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

from aidial_sdk.chat_completion.request import CacheBreakpoint
from aidial_sdk.translators.messages_to_chat_completions.chat_completions.cache_breakpoints import (
    CacheControl,
    to_dial_cache_breakpoint,
)


def marker(*controls: dict[str, object]) -> CacheBreakpoint | None:
    return to_dial_cache_breakpoint(
        [cast(CacheControl, control) for control in controls],
    )


def seconds_from_now(expire_at: str | None) -> float:
    assert expire_at is not None
    return (
        datetime.fromisoformat(expire_at) - datetime.now(UTC)
    ).total_seconds()


def test_no_cache_control_means_no_marker() -> None:
    assert marker() is None


def test_a_cache_control_without_a_ttl_leaves_the_default_alone() -> None:
    breakpoint = marker({"type": "ephemeral"})
    assert breakpoint is not None
    assert breakpoint.expire_at is None


@pytest.mark.parametrize(
    "ttl, expected",
    [
        ("5m", timedelta(minutes=5)),
        ("1h", timedelta(hours=1)),
    ],
)
def test_a_ttl_duration_becomes_an_absolute_instant(
    ttl: object, expected: timedelta
) -> None:
    breakpoint = marker({"type": "ephemeral", "ttl": ttl})
    assert breakpoint is not None
    assert breakpoint.expire_at is not None
    assert breakpoint.expire_at.endswith("Z")
    assert breakpoint.model_dump(exclude_none=True).keys() == {"expire_at"}
    assert seconds_from_now(breakpoint.expire_at) == pytest.approx(
        expected.total_seconds(), abs=2
    )


@pytest.mark.parametrize(
    "ttl", ["", "forever", "5", "m", "5 m", "-1h", "30s", "2d", "0m", 300, []]
)
def test_an_unreadable_ttl_never_costs_the_marker(ttl: object) -> None:
    breakpoint = marker({"type": "ephemeral", "ttl": ttl})
    assert breakpoint is not None
    assert breakpoint.expire_at is None


def test_the_longest_ttl_wins_when_blocks_collapse_onto_one_object() -> None:
    breakpoint = marker(
        {"ttl": "nonsense"},
        {"ttl": "5m"},
        {"ttl": "1h"},
        {"type": "ephemeral"},
        {"ttl": "30s"},
    )
    assert breakpoint is not None
    assert seconds_from_now(breakpoint.expire_at) == pytest.approx(3600, abs=2)


@pytest.mark.parametrize("ttl", ["999999999999999999999h", "9999999999m"])
def test_unrepresentable_expiry_keeps_default_marker(ttl: str) -> None:
    breakpoint = marker({"ttl": ttl})
    assert breakpoint is not None
    assert breakpoint.expire_at is None
