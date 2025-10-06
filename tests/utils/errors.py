from typing import Any

from pydantic import BaseModel

from aidial_sdk._pydantic import PYDANTIC_V2


class Error(BaseModel):
    code: int
    error: dict


def internal_server_error(message: str) -> Error:
    return Error(
        code=500,
        error={
            "error": {
                "code": "500",
                "message": message,
                "type": "runtime_error",
            }
        },
    )


def bad_request_error(message: Any) -> Error:
    return Error(
        code=400,
        error={
            "error": {
                "message": message,
                "type": "invalid_request_error",
                "code": "400",
            }
        },
    )


def invalid_request_error(path: str, message: str) -> Error:
    return bad_request_error(
        f"Your request contained invalid structure on path {path}. {message}"
    )


def missing_fields_error(path: str) -> Error:
    if PYDANTIC_V2:
        return invalid_request_error(path, "Field required")
    else:
        return invalid_request_error(path, "field required")


def extra_fields_error(path: str) -> Error:
    if PYDANTIC_V2:
        return invalid_request_error(path, "Extra inputs are not permitted")
    else:
        return invalid_request_error(path, "extra fields not permitted")


route_not_found_error: Error = Error(code=404, error={"detail": "Not Found"})
