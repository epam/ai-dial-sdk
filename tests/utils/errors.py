from aidial_sdk.pydantic_v1 import BaseModel


class Error(BaseModel):
    code: int
    error: dict


def missing_fields_error(path: str) -> Error:
    return Error(
        code=400,
        error={
            "error": {
                "message": f"Your request contained invalid structure on path {path}. field required",
                "type": "invalid_request_error",
            }
        },
    )


def extra_fields_error(path: str) -> Error:
    return Error(
        code=400,
        error={
            "error": {
                "message": f"Your request contained invalid structure on path {path}. "
                "extra fields not permitted",
                "type": "invalid_request_error",
            }
        },
    )


route_not_found_error: Error = Error(code=404, error={"detail": "Not Found"})
