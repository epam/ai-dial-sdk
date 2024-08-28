from aidial_sdk.pydantic_v1 import BaseModel


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
    return invalid_request_error(path, "field required")


def extra_fields_error(path: str) -> Error:
    return invalid_request_error(path, "extra fields not permitted")


route_not_found_error: Error = Error(code=404, error={"detail": "Not Found"})
