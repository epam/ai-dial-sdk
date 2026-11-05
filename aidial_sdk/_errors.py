from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute

from aidial_sdk._pydantic import ValidationError
from aidial_sdk.exceptions import (
    ExceptionType,
    InternalServerError,
    InvalidRequestError,
)
from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.utils.logging import logger as log

INTERNAL_ERROR_MESSAGE = "Internal server error"

Handler = Callable[[Request], Awaitable[Response]]


def _get_exception_type(request: Request) -> ExceptionType:
    route = request.scope.get("route")
    if isinstance(route, APIRoute) and route.path.startswith("/anthropic/"):
        return "anthropic"
    return "openai"


def invalid_request_error(e: ValidationError) -> InvalidRequestError:
    error = e.errors()[0]
    path = ".".join(map(str, error["loc"]))
    return InvalidRequestError(
        f"Your request contained invalid structure on path {path}. {error['msg']}"
    )


def to_dial_exception(e: Exception) -> DIALException:
    match e:
        case DIALException():
            return e
        case _:
            log.exception("Unexpected error in the request handler")
            return InternalServerError(INTERNAL_ERROR_MESSAGE)


def _error_response(
    request: Request, e: Exception, api: ExceptionType | None
) -> Response:
    if isinstance(e, HTTPException):
        return JSONResponse(
            status_code=e.status_code,
            content=e.detail,
            headers=e.headers,
        )

    api = api or _get_exception_type(request)
    return to_dial_exception(e).to_fastapi_response(api)


def error_handler(api: ExceptionType | None) -> Callable[[Handler], Handler]:
    def _decorator(handler: Handler) -> Handler:
        async def _handler(request: Request) -> Response:
            try:
                return await handler(request)
            except Exception as e:
                return _error_response(request, e, api)

        return _handler

    return _decorator


def dial_exception_handler(request: Request, exc: Exception) -> Response:
    return _error_response(request, exc, None)


def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    # ServerErrorMiddleware re-raises the exception for the server to log it
    error = InternalServerError(
        f"Unhandled SDK exception: {INTERNAL_ERROR_MESSAGE}"
    )
    return _error_response(request, error, None)
