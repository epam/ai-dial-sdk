from pydantic import BaseModel


class Error(BaseModel):
    code: int
    error: dict


def bad_request_error(path: str) -> Error:
    return Error(
        code=400,
        error={
            "error": {
                "code": None,
                "message": f"Your request contained invalid structure on path {path}. field required",
                "param": None,
                "type": "invalid_request_error",
            }
        },
    )


def not_implemented_error(endpoint: str) -> Error:
    return Error(
        code=404,
        error={
            "error": {
                "message": f"The deployment doesn't implement '{endpoint}' endpoint.",
                "type": "runtime_error",
                "code": "endpoint_not_found",
                "param": None,
            }
        },
    )


def extra_fields_error(path: str) -> Error:
    return Error(
        code=400,
        error={
            "error": {
                "code": None,
                "message": f"Your request contained invalid structure on path {path}. "
                "extra fields not permitted",
                "param": None,
                "type": "invalid_request_error",
            }
        },
    )


route_not_found_error: Error = Error(code=404, error={"detail": "Not Found"})
