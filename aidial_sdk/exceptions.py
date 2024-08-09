from http import HTTPStatus
from typing import Optional


class HTTPException(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = 500,
        type: Optional[str] = "runtime_error",
        param: Optional[str] = None,
        code: Optional[str] = None,
        display_message: Optional[str] = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.type = type
        self.param = param
        self.code = code
        self.display_message = display_message

    def __repr__(self):
        return (
            "%s(message=%r, status_code=%r, type=%r, param=%r, code=%r, display_message=%r)"
            % (
                self.__class__.__name__,
                self.message,
                self.status_code,
                self.type,
                self.param,
                self.code,
                self.display_message,
            )
        )


def resource_not_found(message: str, **kwargs) -> HTTPException:
    """
    Thrown by OpenAI when either endpoint is invalid or api-version is unknown
    """
    return HTTPException(
        status_code=HTTPStatus.NOT_FOUND,
        message=message,
        **kwargs,
    )


def deployment_not_found(message: str, **kwargs) -> HTTPException:
    """
    Thrown by OpenAI when the deployment isn't found
    """
    return HTTPException(
        status_code=HTTPStatus.NOT_FOUND,
        code="DeploymentNotFound",
        message=message,
        **kwargs,
    )


def request_validation_error(message: str, **kwargs) -> HTTPException:
    return HTTPException(
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        type="invalid_request_error",
        message=message,
        **kwargs,
    )


def invalid_request_error(message: str, **kwargs) -> HTTPException:
    return HTTPException(
        status_code=HTTPStatus.BAD_REQUEST,
        type="invalid_request_error",
        message=message,
        **kwargs,
    )


def cannot_truncate_prompt_error(message: str, **kwargs) -> HTTPException:
    return HTTPException(
        status_code=HTTPStatus.BAD_REQUEST,
        type="invalid_request_error",
        code="cannot_fit_into_max_prompt_tokens",
        param="max_prompt_tokens",
        message=message,
        **kwargs,
    )


def runtime_server_error(message: str, **kwargs) -> HTTPException:
    return HTTPException(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        type="runtime_error",
        message=message,
        **kwargs,
    )


def internal_server_error(message: str, **kwargs) -> HTTPException:
    return HTTPException(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        type="internal_server_error",
        message=message,
        **kwargs,
    )
