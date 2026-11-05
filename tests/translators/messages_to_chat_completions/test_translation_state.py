import re

import pytest

from aidial_sdk.translators.messages_to_chat_completions.translation_state import (
    TranslationState,
)

CONFORMING = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_-]{0,63}$")

_LONG_MCP_NAME = "mcp__" + "a" * 60 + "__do_the_thing"


@pytest.mark.parametrize(
    "name",
    [
        "get_weather",
        "a",
        "a" * 64,
        "_leading",
        "with-hyphen",
        "Mixed_9",
    ],
)
def test_conforming_names_are_never_touched(name: str) -> None:
    assert TranslationState().to_upstream_tool_name(name) == name


@pytest.mark.parametrize(
    "name",
    [
        _LONG_MCP_NAME,
        "a" * 65,
        "has spaces",
        "dots.and:colons",
        "unicodé",
        "9leading_digit",
        "-leading-hyphen",
    ],
)
def test_non_conforming_names_become_conforming_aliases(name: str) -> None:
    translation_state = TranslationState()
    alias = translation_state.to_upstream_tool_name(name)
    assert alias != name
    assert CONFORMING.match(alias), alias
    assert translation_state.to_client_tool_name(alias) == name


def test_aliasing_is_deterministic_across_states() -> None:
    assert TranslationState().to_upstream_tool_name(
        _LONG_MCP_NAME
    ) == TranslationState().to_upstream_tool_name(_LONG_MCP_NAME)


def test_names_differing_only_past_the_truncation_point_still_differ() -> None:
    translation_state = TranslationState()
    shared = "m" * 80
    assert translation_state.to_upstream_tool_name(
        f"{shared}_one"
    ) != translation_state.to_upstream_tool_name(f"{shared}_two")


def test_an_unregistered_name_is_returned_as_sent() -> None:
    assert (
        TranslationState().to_client_tool_name("never_registered")
        == "never_registered"
    )


def test_aliases_are_scoped_to_their_translation_state() -> None:
    alias = TranslationState().to_upstream_tool_name(_LONG_MCP_NAME)
    assert TranslationState().to_client_tool_name(alias) == alias
