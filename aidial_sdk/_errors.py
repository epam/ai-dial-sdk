from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.exceptions import InvalidRequestError
from aidial_sdk.pydantic_v1 import ValidationError


def pydantic_validation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    assert isinstance(exc, ValidationError)

    error = exc.errors()[0]
    path = ".".join(map(str, error["loc"]))
    message = f"Your request contained invalid structure on path {path}. {error['msg']}"

    return InvalidRequestError(message).to_fastapi_response()


def fastapi_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, HTTPException)
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail,
    )


def dial_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DIALException)
    return exc.to_fastapi_response()
