from importlib.util import find_spec

import pytest

from aidial_sdk._pydantic import PYDANTIC_V2


@pytest.mark.skipif(
    not PYDANTIC_V2 or find_spec("anthropic") is not None,
    reason="Needs Pydantic v2 without the translators extra",
)
def test_the_translator_requires_the_translators_extra():
    with pytest.raises(ImportError) as e:
        import aidial_sdk.translators.messages_to_chat_completions  # noqa: F401

    assert str(e.value) == (
        "The Anthropic Messages API translator requires the translators extra: "
        'pip install "aidial-sdk[translators]"'
    )
