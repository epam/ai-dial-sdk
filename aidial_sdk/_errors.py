from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.pydantic_v1 import ValidationError
from aidial_sdk.utils.errors import json_error


def pydantic_validation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    assert isinstance(exc, ValidationError)

    error = exc.errors()[0]
    path = ".".join(map(str, error["loc"]))
    message = f"Your request contained invalid structure on path {path}. {error['msg']}"
    return JSONResponse(
        status_code=400,
        content=json_error(message=message, type="invalid_request_error"),
    )


def fastapi_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, HTTPException)
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail,
    )


def dial_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DIALException)
    return JSONResponse(
        status_code=exc.status_code,
        content=json_error(
            message=exc.message,
            type=exc.type,
            param=exc.param,
            code=exc.code,
            display_message=exc.display_message,
        ),
    )
