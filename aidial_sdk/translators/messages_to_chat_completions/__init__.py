"""Translator from the Anthropic Messages API to the Chat Completions API.

Exposes the Anthropic Messages API as a mountable sub-application that
serves the requests by calling the Chat Completions API of DIAL Core
at `DIAL_URL`.

Typical usage::

    import httpx
    from aidial_sdk import DIALApp
    from aidial_sdk.translators.messages_to_chat_completions import (
        mount_translator,
    )

    app = DIALApp(...)
    mount_translator(app, httpx.AsyncClient())
"""

import httpx
from starlette.applications import Starlette

from aidial_sdk._pydantic import PYDANTIC_V2

if not PYDANTIC_V2:
    raise ImportError(
        "The Anthropic Messages API translator requires Pydantic v2: "
        "install pydantic>=2 and set PYDANTIC_V2=True"
    )

from aidial_sdk.translators.messages_to_chat_completions.chat_completions.app import (  # noqa: E402
    ClientFactory,
    create_anthropic_api_app,
)

__all__ = ["ClientFactory", "create_anthropic_api_app", "mount_translator"]


def mount_translator(
    app: Starlette,
    get_client: ClientFactory[httpx.AsyncClient],
    *,
    path: str = "/openaiChatCompletions",
    name: str = "Anthropic Messages API to Chat Completions API translator",
) -> None:
    translator = create_anthropic_api_app(get_client)
    app.mount(path=path, app=translator, name=name)
