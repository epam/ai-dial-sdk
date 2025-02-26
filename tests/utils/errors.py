from pydantic import BaseModel

from aidial_sdk._pydantic._compat import PYDANTIC_V2


class Error(BaseModel):
    code: int
    error: dict


def invalid_request_error(path: str, message: str) -> Error:
    return Error(
        code=400,
        error={
            "error": {
                "message": f"Your request contained invalid structure on path {path}. {message}",
                "type": "invalid_request_error",
                "code": "400",
            }
        },
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
