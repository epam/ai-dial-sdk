from importlib import import_module
from importlib.util import find_spec

import pytest

from aidial_sdk import DIALApp
from aidial_sdk._pydantic import PYDANTIC_V2
from tests.applications.noop import NoopApplication


@pytest.mark.skipif(
    not PYDANTIC_V2 or find_spec("anthropic") is not None,
    reason="Needs Pydantic v2 without the translators extra",
)
def test_exposing_anthropic_messages_requires_the_translators_extra():
    with pytest.raises(ImportError) as e:
        DIALApp().add_chat_completion(
            "app", NoopApplication(), expose_as_anthropic_messages=True
        )

    assert str(e.value) == (
        "The Anthropic Messages API translator requires the translators extra: "
        'pip install "aidial-sdk[translators]"'
    )


@pytest.mark.skipif(
    not PYDANTIC_V2 or find_spec("anthropic") is not None,
    reason="Needs Pydantic v2 without the translators extra",
)
def test_the_responses_translator_requires_the_translators_extra():
    with pytest.raises(ImportError) as e:
        import_module("aidial_sdk.translators.messages_to_responses")

    assert str(e.value) == (
        "The Anthropic Messages API translator requires the translators extra: "
        'pip install "aidial-sdk[translators]"'
    )
