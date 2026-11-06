from collections.abc import Callable

import httpx
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import Response

from aidial_sdk._errors import Handler, error_handler
from aidial_sdk.exceptions import ResourceNotFoundError
from aidial_sdk.translators.messages_to_responses.dial_core import (
    ClientFactory,
    dial_core_handler,
)
from aidial_sdk.translators.messages_to_responses.messages_handler import (
    to_messages_handler,
)
from aidial_sdk.utils._logging_middleware import LoggingMiddleware


def expose_as_anthropic_messages(
    app: FastAPI | APIRouter, *, path: str = "/anthropic/v1/messages"
) -> Callable[[Handler], Handler]:
    """Serves an OpenAI Responses API handler under the Anthropic Messages API
    too, at `path` of `app`.

    A Messages request is translated into a Responses request that the handler
    is called with in-process, and the handler's response, streaming or not,
    is translated back::

        @expose_as_anthropic_messages(app)
        @app.post("/openai/v1/responses")
        async def responses(request: Request) -> Response: ...
    """

    def _decorator(handler: Handler) -> Handler:
        app.add_api_route(
            path,
            error_handler("anthropic")(to_messages_handler(handler)),
            methods=["POST"],
        )
        return handler

    return _decorator


async def _not_found(request: Request) -> Response:
    error = ResourceNotFoundError(f"Unknown endpoint: {request.url.path}")
    return error.to_fastapi_response("anthropic")


def create_anthropic_api_app(
    get_client: ClientFactory[httpx.AsyncClient],
) -> FastAPI:
    """An app serving the Anthropic Messages API by the Responses API of
    DIAL Core at `DIAL_URL`."""

    app = FastAPI()
    app.add_middleware(LoggingMiddleware)
    expose_as_anthropic_messages(app)(dial_core_handler(get_client))
    app.add_api_route(
        "/{full_path:path}",
        _not_found,
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    )
    return app


def mount_translator(
    app: FastAPI,
    get_client: ClientFactory[httpx.AsyncClient],
    *,
    path: str = "/openaiResponses",
    name: str = "Anthropic Messages API to Responses API translator",
) -> None:
    app.mount(path=path, app=create_anthropic_api_app(get_client), name=name)
