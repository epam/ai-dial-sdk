from fastapi import FastAPI

from aidial_sdk._pydantic import PYDANTIC_V2

if not PYDANTIC_V2:
    raise ImportError(
        "The Anthropic Messages API translator requires Pydantic v2: "
        "install pydantic>=2 and set PYDANTIC_V2=True"
    )

try:
    import httpx

    from aidial_sdk.translators.messages_to_chat_completions.chat_completions.app import (
        ClientFactory,
        create_anthropic_api_app,
    )
except ModuleNotFoundError as e:
    raise ImportError(
        "The Anthropic Messages API translator requires the translators extra: "
        'pip install "aidial-sdk[translators]"'
    ) from e

__all__ = ["ClientFactory", "create_anthropic_api_app", "mount_translator"]


def mount_translator(
    app: FastAPI,
    get_client: ClientFactory[httpx.AsyncClient],
    *,
    path: str = "/openaiChatCompletions",
    name: str = "Anthropic Messages API to Chat Completions API translator",
) -> None:
    translator = create_anthropic_api_app(get_client)
    app.mount(path=path, app=translator, name=name)
