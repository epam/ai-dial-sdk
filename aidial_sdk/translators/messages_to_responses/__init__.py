from aidial_sdk._pydantic import PYDANTIC_V2

if not PYDANTIC_V2:
    raise ImportError(
        "The Anthropic Messages API translator requires Pydantic v2: "
        "install pydantic>=2 and set PYDANTIC_V2=True"
    )

try:
    from aidial_sdk.translators.messages_to_responses.app import (
        ClientFactory,
        create_anthropic_api_app,
        expose_as_anthropic_messages,
        mount_translator,
    )
except ModuleNotFoundError as e:
    raise ImportError(
        "The Anthropic Messages API translator requires the translators extra: "
        'pip install "aidial-sdk[translators]"'
    ) from e

__all__ = [
    "ClientFactory",
    "create_anthropic_api_app",
    "expose_as_anthropic_messages",
    "mount_translator",
]
